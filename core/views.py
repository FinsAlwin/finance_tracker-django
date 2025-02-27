from django.shortcuts import render, redirect, get_object_or_404
from .models import Transaction, Category, Loan
from .forms import TransactionForm, LoanForm, CategoryForm
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
import os
import requests
from dotenv import load_dotenv
from django.contrib.auth.forms import UserCreationForm
from django.views.generic import UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout, login
import re
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
import csv
from io import StringIO
load_dotenv()

def query_llm(payload):
    """Query Ollama for financial suggestions."""
    try:
        # Try Ollama locally
        ollama_url = "http://localhost:11434/api/generate"
        
        # Get the prompt from the payload
        prompt = payload["inputs"]
        
        # Configure Ollama request
        ollama_payload = {
            "model": "mistral",  # You can change to any model you have in Ollama
            "prompt": prompt,
            "stream": False,
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        # Make the request to Ollama
        response = requests.post(
            ollama_url, 
            json=ollama_payload, 
            timeout=10
        )
        
        # Check if the request was successful
        if response.status_code == 200:
            result = response.json()
            return result.get("response", None)
        else:
            print(f"Ollama API error: {response.status_code} {response.reason}")
            return None
            
    except Exception as e:
        print(f"Ollama error: {str(e)}")
        return None

@login_required
def home(request):
    # Filter transactions by user and order by date descending
    transactions = Transaction.objects.filter(user=request.user).order_by('-date')[:10]
    
    # Calculate monthly stats
    one_month_ago = timezone.now().date() - timedelta(days=30)
    monthly_income = Transaction.objects.filter(
        type='income', 
        date__gte=one_month_ago,
        user=request.user
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    monthly_spending = Transaction.objects.filter(
        type='spending', 
        date__gte=one_month_ago,
        user=request.user
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    balance = monthly_income - monthly_spending
    
    context = {
        'transactions': transactions,
        'monthly_income': monthly_income,
        'monthly_spending': monthly_spending,
        'balance': balance
    }
    
    return render(request, 'core/home.html', context)

@login_required
def add_transaction(request):
    if request.method == 'POST':
        form = TransactionForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            return redirect('transaction_list')
    else:
        form = TransactionForm(user=request.user)
    return render(request, 'core/add.html', {'form': form})

@login_required
def reports(request):
    # Get time period from query param, default to monthly
    period = request.GET.get('period', 'monthly')
    
    # Set date range based on period
    today = timezone.now().date()
    if period == 'daily':
        start_date = today
        title = f"Daily Report ({today})"
    elif period == 'weekly':
        start_date = today - timedelta(days=7)
        title = f"Weekly Report ({start_date} to {today})"
    elif period == 'yearly':
        start_date = today.replace(month=1, day=1)
        title = f"Yearly Report ({today.year})"
    else:  # monthly (default)
        start_date = today.replace(day=1)
        title = f"Monthly Report ({today.strftime('%B %Y')})"
    
    # Query transactions for the selected period
    spending_by_category = Transaction.objects.filter(
        type='spending', 
        date__gte=start_date,
        user=request.user
    ).values('category__name').annotate(total=Sum('amount'))
    
    total_income = Transaction.objects.filter(
        type='income', 
        date__gte=start_date,
        user=request.user
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    context = {
        'spending': spending_by_category,
        'income': total_income,
        'period': period,
        'title': title
    }
    
    return render(request, 'core/reports.html', context)

@login_required
def suggestions(request):
    # Get transaction data from the past month
    one_month_ago = timezone.now().date() - timedelta(days=30)
    transactions = Transaction.objects.filter(
        date__gte=one_month_ago, 
        user=request.user
    ).select_related('category')
    
    # Calculate financial metrics
    total_income = transactions.filter(type='income').aggregate(Sum('amount'))['amount__sum'] or 0
    total_spending = transactions.filter(type='spending').aggregate(Sum('amount'))['amount__sum'] or 0
    savings_rate = round((total_income - total_spending) / total_income * 100, 2) if total_income > 0 else 0
    
    # Calculate spending by category
    spending_by_category = {}
    for t in transactions.filter(type='spending'):
        cat = t.category.name
        spending_by_category[cat] = spending_by_category.get(cat, 0) + t.amount
    
    # Structured prompt for LLM
    prompt = f"""
As a financial advisor, analyze this user's financial data and provide 5 specific, actionable suggestions. 
Each suggestion should start with a clear title, followed by a specific, personalized recommendation.

Financial Summary (past 30 days):
- Total Income: ₹{total_income:,.2f}
- Total Spending: ₹{total_spending:,.2f}
- Savings Rate: {savings_rate}%

Spending breakdown by category:
"""
    
    # Add category breakdown to prompt
    for category, amount in spending_by_category.items():
        percentage = round((amount / total_spending * 100), 1) if total_spending > 0 else 0
        prompt += f"- {category}: ₹{amount:,.2f} ({percentage}%)\n"

    prompt += """
Please format your response as exactly 5 numbered suggestions (1-5), each with:
1. A brief title
2. A detailed, personalized recommendation based on the data

Example format:
1. Budget Optimization: [specific advice about their budget]
2. Savings Strategy: [specific advice about saving]

IMPORTANT: Do not repeat the financial summary I provided, do not include introductions or conclusions, and keep each suggestion concise and actionable.
"""
    
    suggestion_items = []
    ai_suggestion = None
    
    # Only query LLM if user has meaningful data
    if total_income > 0 and total_spending > 0:
        ai_suggestion = query_llm({'inputs': prompt})
    
    if ai_suggestion:
        print("\nLLM Response:")
        print("=" * 80)
        print(ai_suggestion)
        print("=" * 80 + "\n")
        
        # Parse LLM response with improved regex pattern
        suggestion_pattern = r'(\d+)\.\s+([^:]+):\s+(.*?)(?=\d+\.\s+|$)'
        matches = re.findall(suggestion_pattern, ai_suggestion, re.DOTALL)
        
        for _, title, description in matches:
            suggestion_items.append({
                'title': title.strip(),
                'description': description.strip()
            })
    
    # If we couldn't get good suggestions from LLM, use rule-based generator
    if len(suggestion_items) < 5:
        suggestion_items = generate_rule_based_suggestions(
            total_income, 
            total_spending, 
            savings_rate, 
            spending_by_category
        )
    
    # Prepare the spending categories data for the template
    spending_categories = []
    if total_spending > 0:
        for category, amount in spending_by_category.items():
            percentage = round((amount / total_spending * 100), 1)
            spending_categories.append({
                'name': category,
                'amount': amount,
                'percentage': percentage
            })
    
    return render(request, 'core/suggestions.html', {
        'suggestion_items': suggestion_items,
        'total_income': total_income,
        'total_spending': total_spending,
        'savings_rate': savings_rate,
        'spending_categories': spending_categories
    })

@login_required
def add_loan(request):
    if request.method == 'POST':
        form = LoanForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            return redirect('home')
    else:
        form = LoanForm(user=request.user)
    return render(request, 'core/add_loan.html', {'form': form})

def loan_details(request, loan_id):
    loan = get_object_or_404(Loan, pk=loan_id)
    
    # Calculate amortization schedule
    schedule = []
    remaining = loan.principal_amount
    monthly_rate = (loan.interest_rate / 100) / 12
    
    for month in range(1, loan.term_years * 12 + 1):
        interest_payment = remaining * monthly_rate
        principal_payment = loan.monthly_payment - interest_payment
        remaining -= principal_payment
        
        schedule.append({
            'month': month,
            'payment': loan.monthly_payment,
            'principal': principal_payment,
            'interest': interest_payment,
            'remaining': max(0, remaining)
        })
    
    context = {
        'loan': loan,
        'schedule': schedule,
        'total_interest': sum(month['interest'] for month in schedule),
        'total_payments': loan.monthly_payment * loan.term_years * 12
    }
    
    return render(request, 'core/loan_details.html', context)

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'core/register.html', {'form': form})

class LoanUpdateView(UpdateView):
    model = Loan
    form_class = LoanForm
    template_name = 'core/loan_form.html'
    
    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

class LoanDeleteView(DeleteView):
    model = Loan
    success_url = reverse_lazy('construction_dashboard')
    
    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

def custom_logout(request):
    logout(request)
    return redirect('home')

def generate_rule_based_suggestions(income, spending, savings_rate, categories):
    """Generate intelligent rule-based suggestions without needing LLM API."""
    suggestions = []
    
    # Find highest spending category
    if categories:
        highest_cat = max(categories.items(), key=lambda x: x[1])
        highest_name = highest_cat[0]
        highest_amount = highest_cat[1]
        highest_pct = round((highest_amount / spending * 100), 1) if spending > 0 else 0
        
        # Suggestion 1: Focus on highest spending category
        suggestions.append({
            'title': f'Reduce {highest_name} Spending',
            'description': f'Your highest expense is {highest_name} at ₹{highest_amount:,.2f} ({highest_pct}% of total). Consider reducing this by 15-20% by comparing prices, finding alternatives, or cutting unnecessary purchases.'
        })
    
    # Suggestion 2: Savings rate
    target_rate = 20
    if savings_rate < target_rate:
        suggestions.append({
            'title': 'Increase Savings Rate',
            'description': f'Your savings rate is {savings_rate:.1f}%, which is below the recommended 20%. Try to increase this by reviewing subscriptions, negotiating bills, and tracking all expenses for unnecessary spending.'
        })
    else:
        suggestions.append({
            'title': 'Maintain Strong Savings',
            'description': f'Your savings rate of {savings_rate:.1f}% is good. Consider allocating some of your savings (₹{income * 0.1:,.2f} monthly) to investments for long-term growth.'
        })
    
    # Suggestion 3: Emergency fund
    emergency_target = spending * 6
    monthly_contribution = emergency_target / 12
    suggestions.append({
        'title': 'Build Emergency Fund',
        'description': f'Aim to build an emergency fund of ₹{emergency_target:,.2f} (6 months of expenses). Set aside ₹{monthly_contribution:,.2f} monthly in a high-yield savings account for financial security.'
    })
    
    # Suggestion 4: Debt management or investment
    if income > 0:
        suggestions.append({
            'title': 'Smart Investment Strategy',
            'description': f'Consider investing ₹{income * 0.15:,.2f} (15% of income) monthly in a mix of index funds (60%), fixed deposits (30%), and gold (10%) for a balanced portfolio with good returns.'
        })
    
    # Suggestion 5: Expense tracking
    suggestions.append({
        'title': 'Detailed Expense Tracking',
        'description': 'Track every expense for the next 30 days in detail. Categorize each purchase and identify at least 3 areas where you can reduce spending without affecting quality of life.'
    })
    
    return suggestions

@login_required
def transaction_list(request):
    # Get filter parameters
    search = request.GET.get('search', '')
    type_filter = request.GET.get('type', '')
    category_filter = request.GET.get('category', '')
    period = request.GET.get('period', '')
    
    # Base query
    transactions = Transaction.objects.filter(user=request.user)
    
    # Apply time period filter
    today = timezone.now().date()
    if period == 'daily':
        transactions = transactions.filter(date=today)
    elif period == 'weekly':
        start_date = today - timedelta(days=7)
        transactions = transactions.filter(date__gte=start_date)
    elif period == 'monthly':
        start_date = today.replace(day=1)
        transactions = transactions.filter(date__gte=start_date)
    elif period == 'yearly':
        start_date = today.replace(month=1, day=1)
        transactions = transactions.filter(date__gte=start_date)
    
    # Apply other filters
    if search:
        transactions = transactions.filter(
            Q(description__icontains=search) | 
            Q(category__name__icontains=search)
        )
    if type_filter:
        transactions = transactions.filter(type=type_filter)
    if category_filter:
        transactions = transactions.filter(category_id=category_filter)
    
    # Ordering
    transactions = transactions.order_by('-date')
    
    # Pagination
    paginator = Paginator(transactions, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get categories for filter dropdown
    categories = Category.objects.filter(Q(user=request.user) | Q(user__isnull=True))
    
    context = {
        'page_obj': page_obj,
        'categories': categories,
        'search': search,
        'type_filter': type_filter,
        'category_filter': category_filter,
        'period': period
    }
    
    return render(request, 'core/transaction_list.html', context)

class TransactionUpdateView(UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = 'core/add.html'
    success_url = reverse_lazy('transaction_list')
    
    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

class TransactionDeleteView(DeleteView):
    model = Transaction
    success_url = reverse_lazy('transaction_list')
    
    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

@login_required
def add_category(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            return redirect('transaction_list')
    else:
        form = CategoryForm(user=request.user)
    return render(request, 'core/add_category.html', {'form': form})

@login_required
def category_list(request):
    categories = Category.objects.filter(user=request.user)
    return render(request, 'core/category_list.html', {'categories': categories})

@login_required
def edit_category(request, pk):
    category = get_object_or_404(Category, pk=pk, user=request.user)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category, user=request.user)
        if form.is_valid():
            form.save()
            return redirect('category_list')
    else:
        form = CategoryForm(instance=category, user=request.user)
    return render(request, 'core/edit_category.html', {'form': form})

@login_required
def delete_category(request, pk):
    category = get_object_or_404(Category, pk=pk, user=request.user)
    if request.method == 'POST':
        category.delete()
        return redirect('category_list')
    return render(request, 'core/delete_category.html', {'category': category})

@login_required
def export_transactions(request):
    # Get filter parameters
    search = request.GET.get('search', '')
    type_filter = request.GET.get('type', '')
    category_filter = request.GET.get('category', '')
    period = request.GET.get('period', '')
    export_format = request.GET.get('format', 'csv')

    # Base query
    transactions = Transaction.objects.filter(user=request.user)

    # Apply filters (same as transaction_list view)
    today = timezone.now().date()
    if period == 'daily':
        transactions = transactions.filter(date=today)
    elif period == 'weekly':
        start_date = today - timedelta(days=7)
        transactions = transactions.filter(date__gte=start_date)
    elif period == 'monthly':
        start_date = today.replace(day=1)
        transactions = transactions.filter(date__gte=start_date)
    elif period == 'yearly':
        start_date = today.replace(month=1, day=1)
        transactions = transactions.filter(date__gte=start_date)

    if search:
        transactions = transactions.filter(
            Q(description__icontains=search) | 
            Q(category__name__icontains=search)
        )
    if type_filter:
        transactions = transactions.filter(type=type_filter)
    if category_filter:
        transactions = transactions.filter(category_id=category_filter)

    # Ordering
    transactions = transactions.order_by('-date')

    if export_format == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="transactions.csv"'

        writer = csv.writer(response)
        writer.writerow(['Date', 'Type', 'Category', 'Description', 'Amount'])

        for t in transactions:
            writer.writerow([
                t.date.strftime('%Y-%m-%d'),
                t.get_type_display(),
                t.category.name,
                t.description,
                t.amount
            ])

        return response

    elif export_format == 'pdf':
        template = get_template('core/transactions_pdf.html')
        context = {'transactions': transactions}
        html = template.render(context)

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="transactions.pdf"'

        pisa_status = pisa.CreatePDF(html, dest=response)
        if pisa_status.err:
            return HttpResponse('We had some errors generating the PDF')
        return response