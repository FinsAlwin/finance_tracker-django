from django import forms
from .models import Transaction, Loan, Category
from django.db.models import Q
import datetime

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['type', 'date', 'amount', 'category', 'description']
        widgets = {
            'date': forms.DateInput(attrs={
                'type': 'date',
                'value': datetime.date.today().strftime('%Y-%m-%d')
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['category'].queryset = Category.objects.filter(
                Q(user=self.user) | Q(user__isnull=True)
            )
        # Set initial date value
        self.fields['date'].initial = datetime.date.today()
        
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.user = self.user
        if commit:
            instance.save()
        return instance

class LoanForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = ['name', 'principal_amount', 'interest_rate', 'term_years', 'start_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.user = self.user
        if commit:
            instance.save()
        return instance

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name']
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
    def save(self, commit=True):
        instance = super().save(commit=False)
        # Ensure the category belongs to the current user
        instance.user = self.user
        if commit:
            instance.save()
        return instance