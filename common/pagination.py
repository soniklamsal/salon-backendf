"""Pagination for the router-backed list endpoints.

The aggregate endpoints the frontend actually uses — `/homepage/`,
`/booking-config/` — build their responses by hand and are unaffected by this.
It applies to the per-resource lists, which are unbounded by construction even
though every one of them is small today.
"""

from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 200