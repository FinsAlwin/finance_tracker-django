from django.contrib import admin
from .models import Transaction, Category
from django.db.models import Q

# Register basic model view
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'user')
    list_filter = ('user',)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(Q(user=request.user) | Q(user__isnull=True))

admin.site.register(Category, CategoryAdmin)
admin.site.register(Transaction)

# Alternatively, for a more customized admin interface:
# @admin.register(Transaction)
# class TransactionAdmin(admin.ModelAdmin):
#     list_display = ('date', 'type', 'category', 'amount', 'description')
#     list_filter = ('type', 'category', 'date')
#     search_fields = ('description', 'category__name')
#     date_hierarchy = 'date'
# 
# @admin.register(Category)
# class CategoryAdmin(admin.ModelAdmin):
#     list_display = ('name',)
#     search_fields = ('name',)
