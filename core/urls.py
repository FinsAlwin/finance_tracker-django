from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.home, name='home'),
    path('add/', views.add_transaction, name='add_transaction'),
    path('reports/', views.reports, name='reports'),
    path('suggestions/', views.suggestions, name='suggestions'),
    path('loans/add/', views.add_loan, name='add_loan'),
    path('loans/<int:loan_id>/', views.loan_details, name='loan_details'),
    path('accounts/login/', auth_views.LoginView.as_view(), name='login'),
    path('accounts/logout/', views.custom_logout, name='logout'),
    path('accounts/register/', views.register, name='register'),
    path('loans/<int:pk>/edit/', views.LoanUpdateView.as_view(), name='edit_loan'),
    path('loans/<int:pk>/delete/', views.LoanDeleteView.as_view(), name='delete_loan'),
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/<int:pk>/edit/', views.TransactionUpdateView.as_view(), name='edit_transaction'),
    path('transactions/<int:pk>/delete/', views.TransactionDeleteView.as_view(), name='delete_transaction'),
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.add_category, name='add_category'),
    path('categories/<int:pk>/edit/', views.edit_category, name='edit_category'),
    path('categories/<int:pk>/delete/', views.delete_category, name='delete_category'),
    path('transactions/export/', views.export_transactions, name='export_transactions'),
]