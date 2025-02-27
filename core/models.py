from django.db import models
from django.db.models import Sum
from django.contrib.auth.models import User

class Category(models.Model):
    name = models.CharField(max_length=50)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        unique_together = ('name', 'user')  # Ensure category names are unique per user

    def __str__(self):
        return self.name

class Transaction(models.Model):
    TYPE_CHOICES = [
        ('spending', 'Spending'),
        ('income', 'Income'),
    ]
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    date = models.DateField()
    amount = models.FloatField()
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    description = models.TextField(blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_construction_expense = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.type} - {self.category.name} - ${self.amount}"

class Loan(models.Model):
    name = models.CharField(max_length=100)
    principal_amount = models.FloatField()
    interest_rate = models.FloatField(help_text="Annual interest rate in percentage")
    term_years = models.IntegerField()
    start_date = models.DateField()
    monthly_payment = models.FloatField(blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.name} - ₹{self.principal_amount}"
    
    def calculate_monthly_payment(self):
        # Calculate EMI: P × r × (1 + r)^n / ((1 + r)^n - 1)
        # P: principal, r: monthly interest rate, n: number of months
        monthly_rate = (self.interest_rate / 100) / 12
        n_payments = self.term_years * 12
        
        if monthly_rate == 0:
            return self.principal_amount / n_payments
            
        x = (1 + monthly_rate) ** n_payments
        emi = self.principal_amount * monthly_rate * x / (x - 1)
        
        return round(emi, 2)
    
    def save(self, *args, **kwargs):
        if not self.monthly_payment:
            self.monthly_payment = self.calculate_monthly_payment()
        super().save(*args, **kwargs)