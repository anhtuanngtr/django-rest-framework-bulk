Django REST Framework Bulk
==========================

Django REST Framework bulk CRUD view mixins.

Overview
--------

Django REST Framework comes with many generic views however none
of them allow to do bulk operations such as create, update and delete.
To keep the core of Django REST Framework simple, its maintainer
suggested to create a separate project to allow for bulk operations
within the framework. That is the purpose of this project.

Requirements
------------

* Python>=2.7
* Django>=1.3
* Django REST Framework >= 3.0.0
* REST Framework >= 2.2.5
  (**only with** Django<1.8 since DRF<3 does not support Django1.8)

Installing
----------

Using pip::

    // To be updated

or from source code::

    $ pip install -e git+http://github.com/anhtuanngtr/django-rest-framework-bulk#egg=djangorestframework-bulk

Example
-------

The bulk views (and mixins) are very similar to Django REST Framework's own
generic views (and mixins)::

    from rest_framework_bulk import (
        BulkListSerializer,
        BulkSerializerMixin,
        ListBulkCreateUpdateDestroyAPIView,
    )

    class FooSerializer(BulkSerializerMixin, ModelSerializer):
        class Meta(object):
            model = FooModel
            # only necessary in DRF3
            list_serializer_class = BulkListSerializer

    class FooView(ListBulkCreateUpdateDestroyAPIView):
        queryset = FooModel.objects.all()
        serializer_class = FooSerializer

The above will allow to create the following queries

::

    # list queryset
    GET

::

    # create single resource
    POST
    {"field":"value","field2":"value2"}     <- json object in request data

::

    # create multiple resources
    POST
    [{"field":"value","field2":"value2"}]

::

    # update multiple resources (requires all fields)
    PUT
    [{"field":"value","field2":"value2"}]   <- json list of objects in data

::

    # partial update multiple resources
    PATCH
    [{"field":"value"}]                     <- json list of objects in data

::

    # delete queryset (see notes)
    DELETE

Router
------

The bulk router can automatically map the bulk actions::

    from rest_framework_bulk.routes import BulkRouter

    class UserViewSet(BulkModelViewSet):
        model = User

        def allow_bulk_destroy(self, qs, filtered):
            """Don't forget to fine-grain this method"""

    router = BulkRouter()
    router.register(r'users', UserViewSet)

Notes
-----

Most API urls have two URL levels for each resource::

    1. ``url(r'foo/', ...)``
    2. ``url(r'foo/(?P<pk>\d+)/', ...)``

The second url however is not applicable for bulk operations because
the url directly maps to a single resource. Therefore all bulk
generic views only apply to the first url.

There are multiple generic view classes in case only a certail
bulk functionality is required. For example ``ListBulkCreateAPIView``
will only do bulk operations for creating resources.
For a complete list of available generic view classes, please
take a look at the source code at ``generics.py`` as it is mostly
self-explanatory.

Most bulk operations are pretty safe in terms of how they operate,
that is you explicitly describe all requests. For example, if you
need to update 3 specific resources, you have to explicitly identify
those resources in the request's ``PUT`` or ``PATCH`` data.
The only exception to this is bulk delete. Consider a ``DELETE``
request to the first url. That can potentially delete all resources
without any special confirmation. To try to account for this, bulk delete
mixin allows to implement a hook to determine if the bulk delete
request should be allowed::

    class FooView(BulkDestroyAPIView):
        def allow_bulk_destroy(self, qs, filtered):
            # custom logic here

            # default checks if the qs was filtered
            # qs comes from self.get_queryset()
            # filtered comes from self.filter_queryset(qs)
            return qs is not filtered

By default it checks if the queryset was filtered and if not will not
allow the bulk delete to complete. The logic here is that if the request
is filtered to only get certain resources, more attention was payed hence
the action is less likely to be accidental. On how to filter requests,
please refer to Django REST
`docs <http://www.django-rest-framework.org/api-guide/filtering>`_.
Either way, please use bulk deletes with extreme caution since they
can be dangerous.
