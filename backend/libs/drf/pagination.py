from rest_framework.pagination import PageNumberPagination as DjangoPageNumberPagination


class PageNumberPagination(DjangoPageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100
