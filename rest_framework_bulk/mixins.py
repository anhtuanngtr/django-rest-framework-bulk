from __future__ import print_function, unicode_literals

import re

from rest_framework import status
from rest_framework.exceptions import ValidationError, ParseError, _get_full_details
from rest_framework.mixins import CreateModelMixin
from rest_framework.response import Response

__all__ = [
    'BulkCreateModelMixin',
    'BulkDestroyModelMixin',
    'BulkUpdateModelMixin',
]


class BulkCreateModelMixin(CreateModelMixin):
    """
    Either create a single or many model instances in bulk by using the
    Serializers ``many=True`` ability from Django REST >= 2.2.5.

    .. note::
        This mixin uses the same method to create model instances
        as ``CreateModelMixin`` because both non-bulk and bulk
        requests will use ``POST`` request method.
    """

    def create(self, request, *args, **kwargs):
        bulk = isinstance(request.data, list)

        if not bulk:
            return super(BulkCreateModelMixin, self).create(request, *args, **kwargs)

        else:
            serializer = self.get_serializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)
            self.perform_bulk_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_bulk_create(self, serializer):
        return self.perform_create(serializer)


class BulkUpdateModelMixin(object):
    """
    Update model instances in bulk by using the Serializers
    ``many=True`` ability from Django REST >= 2.2.5.
    """

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field

        if lookup_url_kwarg in self.kwargs:
            return super(BulkUpdateModelMixin, self).get_object()

        # If the lookup_url_kwarg is not present
        # get_object() is most likely called as part of options()
        # which by default simply checks for object permissions
        # and raises permission denied if necessary.
        # Here we don't need to check for general permissions
        # and can simply return None since general permissions
        # are checked in initial() which always gets executed
        # before any of the API actions (e.g. create, update, etc)
        return

    def bulk_update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)

        # restrict the update to the filtered queryset
        serializer = self.get_serializer(
            self.filter_queryset(self.get_queryset()),
            data=request.data,
            many=True,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        self.perform_bulk_update(serializer)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def partial_bulk_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.bulk_update(request, *args, **kwargs)

    def perform_update(self, serializer):
        serializer.save()

    def perform_bulk_update(self, serializer):
        return self.perform_update(serializer)


class BulkDestroyModelMixin(object):
    """
    Destroy model instances.
    """

    def allow_bulk_destroy(self, qs, filtered):
        """
        Hook to ensure that the bulk destroy should be allowed.

        By default this checks that the destroy is only applied to
        filtered querysets.
        """
        return qs is not filtered

    def bulk_destroy(self, request, *args, **kwargs):
        qs = self.get_queryset()

        filtered = self.filter_queryset(qs)
        if not self.allow_bulk_destroy(qs, filtered):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        self.perform_bulk_destroy(filtered)

        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        instance.delete()

    def perform_bulk_destroy(self, objects):
        for obj in objects:
            self.perform_destroy(obj)


class EasyBulkCreateModelMixin(object):

    def create(self, request, *args, **kwargs):
        bulk = isinstance(request.data, list)

        if not bulk:
            return super().create(request, *args, **kwargs)

        else:
            serializer = self.get_serializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=False)

            errors = []
            if serializer.errors:
                errors = serializer.errors
                # reset errors here in order for model updates works
                serializer._errors = []

            # Perform blind data change
            self.perform_bulk_create(serializer)

            if errors:
                response = build_multi_status_response(serializer.data, errors)

                return Response(response, status=status.HTTP_207_MULTI_STATUS)

            return Response(serializer.data, status=status.HTTP_201_CREATED)


class EasyBulkUpdateModelMixin(object):

    def bulk_update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)

        # restrict the update to the filtered queryset
        serializer = self.get_serializer(
            self.filter_queryset(self.get_queryset()),
            data=request.data,
            many=True,
            partial=partial,
        )
        serializer.is_valid(raise_exception=False)

        errors = []
        if serializer.errors:
            errors = serializer.errors
            # reset errors here in order for model updates works
            serializer._errors = []
        # raise exception if format is wrong
        if isinstance(errors, dict) and errors.get('non_field_errors')[0].code == 'not_a_list':
            raise ValidationError(errors.get('non_field_errors')[0])

        # Perform blind data change
        self.perform_bulk_update(serializer)

        if errors:
            response = build_multi_status_response(serializer.data, errors)

            return Response(response, status=status.HTTP_207_MULTI_STATUS)

        return Response(serializer.data, status=status.HTTP_200_OK)


class EasyBulkDestroyModelMixin(object):
    def bulk_destroy(self, request, *args, **kwargs):
        list_id = []
        ids = self.request.query_params.get('ids')
        if ids:
            if not re.match(r'^\d+(,\d+)*$', ids):
                raise ParseError("Invalid ids")

            list_id = ids.split(',')
        qs = self.get_queryset().filter(id__in=list_id)

        filtered = self.filter_queryset(qs)
        if not self.allow_bulk_destroy(qs, filtered):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        self.perform_bulk_destroy(filtered)

        return Response(status=status.HTTP_204_NO_CONTENT)


def build_multi_status_response(data, errors):
    response = []
    for error in errors:
        record = {}
        if error:
            record['successful'] = False
            record['errors'] = {key: _get_full_details(error_list) for key, error_list in error.items()}
        else:
            record['successful'] = True
            record['resource'] = data.pop(0) if data else None

        response.append(record)

    return response
