from __future__ import print_function, unicode_literals

import inspect

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from rest_framework.exceptions import ValidationError
from rest_framework.fields import empty, SkipField
from rest_framework.serializers import ListSerializer, as_serializer_error
from rest_framework.settings import api_settings
from rest_framework.utils import html
from rest_framework.utils.serializer_helpers import ReturnList

__all__ = [
    'BulkListSerializer',
    'BulkSerializerMixin',
]


class BulkSerializerMixin(object):
    def to_internal_value(self, data):
        ret = super(BulkSerializerMixin, self).to_internal_value(data)

        id_attr = getattr(self.Meta, 'update_lookup_field', 'id')
        request_method = getattr(getattr(self.context.get('view'), 'request'), 'method', '')

        # add update_lookup_field field back to validated data
        # since super by default strips out read-only fields
        # hence id will no longer be present in validated_data
        if all((isinstance(self.root, BulkListSerializer),
                id_attr,
                request_method in ('PUT', 'PATCH'))):
            id_field = self.fields[id_attr]
            id_value = id_field.get_value(data)

            ret[id_attr] = id_value

        return ret


class BulkListSerializer(ListSerializer):
    update_lookup_field = 'id'

    def update(self, queryset, all_validated_data):
        id_attr = getattr(self.child.Meta, 'update_lookup_field', 'id')

        all_validated_data_by_id = {
            i.pop(id_attr): i
            for i in all_validated_data
        }

        if not all((bool(i) and not inspect.isclass(i)
                    for i in all_validated_data_by_id.keys())):
            raise ValidationError('')

        # since this method is given a queryset which can have many
        # model instances, first find all objects to update
        # and only then update the models
        objects_to_update = queryset.filter(**{
            '{}__in'.format(id_attr): all_validated_data_by_id.keys(),
        })

        if len(all_validated_data_by_id) != objects_to_update.count():
            raise ValidationError('Could not find all objects to update.')

        updated_objects = []

        for obj in objects_to_update:
            obj_id = getattr(obj, id_attr)
            obj_validated_data = all_validated_data_by_id.get(obj_id)

            # use model serializer to actually update the model
            # in case that method is overwritten
            updated_objects.append(self.child.update(obj, obj_validated_data))

        return updated_objects


class EasyBulkListSerializer(BulkListSerializer):
    def __init__(self, *args, **kwargs):
        self.allow_errors = kwargs.pop('allow_errors', True)
        super().__init__(*args, **kwargs)

    def is_valid(self, raise_exception=False):
        # This implementation is the same as the default,
        # except that we use lists, rather than dicts, as the empty case.
        assert hasattr(self, 'initial_data'), (
            'Cannot call `.is_valid()` as no `data=` keyword argument was '
            'passed when instantiating the serializer instance.'
        )

        if not hasattr(self, '_validated_data'):
            try:
                result = self.run_validation(self.initial_data)
                if isinstance(result, dict):
                    self._validated_data = result.get('value')
                    if any(result.get('errors')):
                        raise ValidationError(result.get('errors', []))
                else:
                    self._validated_data = result
            except ValidationError as exc:
                if raise_exception:
                    self._validated_data = []

                self._errors = exc.detail
            else:
                self._errors = []

        if self._errors and raise_exception:
            raise ValidationError(self.errors)

        return not bool(self._errors)

    def run_validation(self, data=empty):
        """
        We override the default `run_validation`, because the validation
        performed by validators and the `.validate()` method should
        be coerced into an error dictionary with a 'non_fields_error' key.
        """
        (is_empty_value, data) = self.validate_empty_values(data)
        if is_empty_value:
            return data

        result = self.to_internal_value(data)
        assert isinstance(result, dict), '.to_internal_value() should return the dict data type'

        value = result.get('ret')
        errors = result.get('errors')
        try:
            self.run_validators(value)
            value = self.validate(value)
            assert value is not None, '.validate() should return the validated data'
        except (ValidationError, DjangoValidationError) as exc:
            raise ValidationError(detail=as_serializer_error(exc))

        return {'value': value, 'errors': errors}

    def to_internal_value(self, data):
        """
        List of dicts of native values <- List of dicts of primitive datatypes.
        """
        if html.is_html_input(data):
            data = html.parse_html_list(data)

        if not isinstance(data, list):
            message = self.error_messages['not_a_list'].format(
                input_type=type(data).__name__
            )
            raise ValidationError({
                api_settings.NON_FIELD_ERRORS_KEY: [message]
            }, code='not_a_list')

        if not self.allow_empty and len(data) == 0:
            if self.parent and self.partial:
                raise SkipField()

            message = self.error_messages['empty']
            raise ValidationError({
                api_settings.NON_FIELD_ERRORS_KEY: [message]
            }, code='empty')

        id_attr = getattr(self.child.Meta, 'update_lookup_field', 'id')
        ret = []
        errors = []

        for item in data:
            try:
                view = self.context.get('view')
                if view and view.action != 'create':
                    if id_attr not in item:
                        raise ValidationError({id_attr: ['This field is required.']})

                    instance = self.instance.get(**{id_attr: item[id_attr]})

                    self.child.instance = instance
                    self.child.initial_data = item
                # Until here
                validated = self.child.run_validation(item)
            except ValidationError as exc:
                errors.append(exc.detail)
            else:
                ret.append(validated)
                errors.append({})

        return {'ret': ret, 'errors': errors}

    def to_representation(self, data):
        """
        List of object instances -> List of dicts of primitive datatypes.
        """
        # Dealing with nested relationships, data can be a Manager,
        # so, first get a queryset from the Manager if needed
        iterable = data.all() if isinstance(data, models.Manager) else data

        if iterable and hasattr(self, '_errors'):
            old_iterable = iterable
            error_positions = [i for i, x in enumerate(self._errors) if x]
            iterable = [v for i, v in enumerate(old_iterable) if i not in error_positions]

        return [
            self.child.to_representation(item) for item in iterable
        ]

    @property
    def data(self):
        if hasattr(self, 'initial_data') and not hasattr(self, '_validated_data'):
            msg = (
                'When a serializer is passed a `data` keyword argument you '
                'must call `.is_valid()` before attempting to access the '
                'serialized `.data` representation.\n'
                'You should either call `.is_valid()` first, '
                'or access `.initial_data` instead.'
            )
            raise AssertionError(msg)

        if not hasattr(self, '_data'):
            if self.instance is not None and (not getattr(self, '_errors', None) or self.allow_errors):
                self._data = self.to_representation(self.instance)
            elif hasattr(self, '_validated_data') and (not getattr(self, '_errors', None) or self.allow_errors):
                self._data = self.to_representation(self.validated_data)
            else:
                self._data = self.get_initial()

        return ReturnList(self._data, serializer=self)
