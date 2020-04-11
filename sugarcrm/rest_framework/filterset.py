from django_filters.rest_framework import filterset


class FilterSet(filterset.FilterSet):
    def filter_queryset(self, queryset):
        for name, value in self.form.cleaned_data.items():
            queryset = self.filters[name].filter(queryset, value)
        return queryset