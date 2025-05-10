from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
import csv
import pandas as pd

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Replace with a secure key

# Configure the database
# SQLite database file
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///financly.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize the database
db = SQLAlchemy(app)

# Initialize Flask-Migrate
migrate = Migrate(app, db)

# User model


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

# Bank model


class Bank(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    balance = db.Column(db.Float, nullable=False, default=0.0)

    # Relationship with Transaction
    transactions = db.relationship(
        "Transaction",
        backref="bank",
        cascade="all, delete-orphan",  # Enable cascade delete
        lazy=True
    )

# Transaction model


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # e.g., deposit, withdraw, expense_payment
    type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    bank_id = db.Column(db.Integer, db.ForeignKey(
        "bank.id", name="fk_transaction_bank_id"), nullable=False)
    expense_id = db.Column(db.Integer, db.ForeignKey(
        "expense.id", name="fk_transaction_expense_id"), nullable=True)  # Link to Expense

# Expense model


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    paid = db.Column(db.Float, nullable=False, default=0.0)

    # Relationship with Transaction
    transactions = db.relationship(
        "Transaction",
        backref="expense",
        cascade="all, delete-orphan",  # Enable cascade delete
        lazy=True
    )

# Inventory model


class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    selling_price = db.Column(db.Float, nullable=False)
    color = db.Column(db.String(50))
    size = db.Column(db.String(50))


# In-memory storage for banks and expenses
banks = {}
expenses = []
default_bank = None  # Default bank for payments

# In-memory storage for inventory
inventory = []

# In-memory storage for users
users = {}  # Format: {"username": {"password": "hashed_password"}}


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        confirm_password = request.form["confirm_password"].strip()

        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash("Username already exists. Please choose a different one.", "error")
            return redirect(url_for("signup"))

        # Check if passwords match
        if password != confirm_password:
            flash("Passwords do not match. Please try again.", "error")
            return redirect(url_for("signup"))

        # Hash the password and create a new user
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash("Signup successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        # Find the user in the database
        user = User.query.filter_by(username=username).first()

        # Check if user exists and password is correct
        if user and check_password_hash(user.password, password):
            session["user"] = username
            flash("Login successful!", "success")
            return redirect(url_for("cash_flow"))
        else:
            flash("Invalid username or password. Please try again.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# Protect routes that require authentication
@app.before_request
def require_login():
    allowed_routes = ["login", "signup",
                      "logout", "init_db", "set_default_bank"]
    if "user" not in session and request.endpoint not in allowed_routes:
        return redirect(url_for("login"))


@app.route("/")
def home():
    return redirect(url_for("cash_flow"))


@app.route("/cash_flow", methods=["GET", "POST"])
def cash_flow():
    if request.method == "POST":
        # Handle adding a new bank
        if "new_bank_name" in request.form:
            bank_name = request.form["new_bank_name"].strip()
            if bank_name:
                # Check if the bank already exists
                existing_bank = Bank.query.filter_by(name=bank_name).first()
                if (existing_bank):
                    flash("Bank already exists!", "error")
                else:
                    # Add the new bank to the database
                    new_bank = Bank(name=bank_name, balance=0.0)
                    db.session.add(new_bank)
                    db.session.commit()
                    flash("Bank added successfully!", "success")
            else:
                flash("Bank name cannot be empty.", "error")

        # Handle deposit or withdrawal
        elif "bank_name" in request.form and "transaction_type" in request.form:
            bank_name = request.form["bank_name"]
            transaction_type = request.form["transaction_type"]
            amount = float(request.form["amount"])
            description = request.form.get("description", "").strip()

            # Find the bank
            bank = Bank.query.filter_by(name=bank_name).first()
            if not bank:
                flash("Bank not found!", "error")
            else:
                if transaction_type == "deposit":
                    # Perform deposit
                    bank.balance += amount
                    new_transaction = Transaction(
                        type="deposit",
                        amount=amount,
                        description=description,
                        bank_id=bank.id
                    )
                    db.session.add(new_transaction)
                    db.session.commit()
                    flash(
                        f"Deposited {amount:.2f} BHD into {bank_name}.", "success")
                elif transaction_type == "withdraw":
                    # Perform withdrawal
                    if bank.balance >= amount:
                        bank.balance -= amount
                        new_transaction = Transaction(
                            type="withdraw",
                            amount=amount,
                            description=description,
                            bank_id=bank.id
                        )
                        db.session.add(new_transaction)
                        db.session.commit()
                        flash(
                            f"Withdrew {amount:.2f} BHD from {bank_name}.", "success")
                    else:
                        flash("Insufficient funds for withdrawal.", "error")

        # Handle deleting a bank
        elif "delete_bank_name" in request.form:
            bank_name = request.form["delete_bank_name"]
            bank = Bank.query.filter_by(name=bank_name).first()
            if bank:
                db.session.delete(bank)
                db.session.commit()
                flash(f"Bank {bank_name} deleted successfully.", "success")
            else:
                flash("Bank not found!", "error")

    # Fetch all banks and transactions from the database
    banks = Bank.query.all()
    transactions = Transaction.query.order_by(
        Transaction.timestamp.desc()).all()

    # Add bank name to each transaction
    transactions_with_bank_name = [
        {
            "bank_name": transaction.bank.name,
            "type": transaction.type,
            "amount": transaction.amount,
            "description": transaction.description,
            "timestamp": transaction.timestamp
        }
        for transaction in transactions
    ]

    # Calculate total deposits and withdrawals for each bank
    bank_totals = {}
    for transaction in transactions:
        if transaction.bank.name not in bank_totals:
            bank_totals[transaction.bank.name] = {
                "deposits": 0.0, "withdrawals": 0.0}
        if transaction.type == "deposit":
            bank_totals[transaction.bank.name]["deposits"] += transaction.amount
        elif transaction.type == "withdraw":
            bank_totals[transaction.bank.name]["withdrawals"] += transaction.amount

    # Calculate overall totals
    total_deposits = sum(t.amount for t in transactions if t.type == "deposit")
    total_withdrawals = sum(
        t.amount for t in transactions if t.type == "withdraw")

    return render_template(
        "cash_flow.html",
        banks=banks,
        transactions=transactions_with_bank_name,
        total_deposits=total_deposits,
        total_withdrawals=total_withdrawals,
        bank_totals=bank_totals
    )


@app.route("/monthly_expenses", methods=["GET", "POST"])
def monthly_expenses():
    # Fetch all banks and expenses from the database
    banks = Bank.query.all()
    expenses = Expense.query.all()

    if request.method == "POST":
        print("Form data received:", request.form)

        if "expense_name" in request.form and "expense_amount" in request.form:
            print("Adding expense:",
                  request.form["expense_name"], request.form["expense_amount"])

        elif "delete_expense" in request.form:
            print("Deleting expense ID:", request.form["delete_expense"])

        # Handle paying an expense
        if "expense_id" in request.form and "amount_paid" in request.form:
            print("Pay Expense request received:", request.form)
            expense_id = int(request.form["expense_id"])
            amount_paid = float(request.form["amount_paid"])
            bank_id = request.form.get("bank_id")
            print(
                f"Expense ID: {expense_id}, Amount Paid: {amount_paid}, Bank ID: {bank_id}")

            # Find the bank and expense
            bank = Bank.query.get(bank_id)
            expense = Expense.query.get(expense_id)

            if not bank:
                flash("Bank not found!", "error")
            elif not expense:
                flash("Expense not found!", "error")
            else:
                remaining_amount = expense.amount - expense.paid

                if amount_paid > remaining_amount:
                    flash(
                        f"Cannot pay more than the remaining amount ({remaining_amount:.2f} BHD).", "error")
                elif bank.balance >= amount_paid:
                    # Update expense and bank balance
                    expense.paid += amount_paid
                    bank.balance -= amount_paid

                    # Add the payment to the transaction history
                    new_transaction = Transaction(
                        type="expense_payment",
                        amount=amount_paid,
                        description=f"Payment for {expense.name}",
                        bank_id=bank.id,
                        expense_id=expense.id
                    )
                    db.session.add(new_transaction)
                    db.session.commit()

                    flash(
                        f"Paid {amount_paid:.2f} BHD for '{expense.name}' using {bank.name}.", "success")
                else:
                    flash("Insufficient funds in the selected bank.", "error")

            # Redirect to avoid form resubmission
            return redirect(url_for("monthly_expenses"))

        # Handle adding a new expense
        if "expense_name" in request.form and "expense_amount" in request.form:
            expense_name = request.form["expense_name"].strip()
            expense_amount = float(request.form["expense_amount"])
            if expense_name and expense_amount > 0:
                new_expense = Expense(
                    name=expense_name, amount=expense_amount, paid=0.0)
                db.session.add(new_expense)
                db.session.commit()
                flash(
                    f"Expense '{expense_name}' added successfully!", "success")
            else:
                flash("Invalid expense name or amount.", "error")

            # Redirect to avoid form resubmission
            return redirect(url_for("monthly_expenses"))

        # Handle deleting an expense
        elif "delete_expense" in request.form:
            expense_id = int(request.form["delete_expense"])
            expense = Expense.query.get(expense_id)
            if expense:
                # Delete related transactions
                related_transactions = Transaction.query.filter_by(
                    expense_id=expense.id).all()
                for transaction in related_transactions:
                    db.session.delete(transaction)

                # Delete the expense
                db.session.delete(expense)
                db.session.commit()
                flash(
                    f"Expense '{expense.name}' deleted successfully!", "success")
            else:
                flash("Expense not found!", "error")

            # Redirect to avoid form resubmission
            return redirect(url_for("monthly_expenses"))

    # Calculate totals
    total_expenses = sum(expense.amount for expense in expenses)
    total_paid = sum(expense.paid for expense in expenses)
    total_remaining = total_expenses - total_paid

    # Fetch transactions related to expense payments
    expense_transactions = Transaction.query.filter_by(
        type="expense_payment").order_by(Transaction.timestamp.desc()).all()

    return render_template(
        "monthly_expenses.html",
        banks=banks,
        expenses=expenses,
        total_expenses=total_expenses,
        total_paid=total_paid,
        total_remaining=total_remaining,
        expense_transactions=expense_transactions
    )


@app.route("/transactions", methods=["GET", "POST"])
def transactions():
    # Fetch all banks from the database
    banks = Bank.query.all()

    # Initialize an empty list to store all transactions
    all_transactions = []

    # Collect all transactions from all banks
    for bank in banks:
        for transaction in bank.transactions:
            all_transactions.append({
                "bank_name": bank.name,
                "type": transaction.type,
                "amount": transaction.amount,
                "description": transaction.description,
                "timestamp": transaction.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            })

    # Sort transactions by timestamp (newest first)
    all_transactions.sort(key=lambda x: x["timestamp"], reverse=True)

    # Filter transactions by date and bank if filters are applied
    filtered_transactions = all_transactions
    if request.method == "POST":
        start_date = request.form.get("start_date")
        end_date = request.form.get("end_date")
        bank_name = request.form.get("bank_name")
        transaction_type = request.form.get("transaction_type")

        if start_date and end_date:
            filtered_transactions = [
                t for t in filtered_transactions
                if start_date <= t["timestamp"][:10] <= end_date
            ]

        if bank_name:
            filtered_transactions = [
                t for t in filtered_transactions if t["bank_name"] == bank_name
            ]

        if transaction_type:
            filtered_transactions = [
                t for t in filtered_transactions if t["type"] == transaction_type
            ]

    return render_template("transactions.html", transactions=filtered_transactions, banks=banks)


@app.route("/inventory", methods=["GET", "POST"])
def inventory_page():
    global inventory

    if request.method == "POST":
        # Add a new inventory item
        if (
            "item_brand" in request.form and
            "item_name" in request.form and
            "item_sku" in request.form and
            "item_quantity" in request.form and
            "item_cost" in request.form and
            "item_selling_price" in request.form and
            "item_color" in request.form and
            "item_size" in request.form
        ):
            item_brand = request.form["item_brand"].strip()
            item_name = request.form["item_name"].strip()
            item_sku = request.form["item_sku"].strip()
            item_quantity = int(request.form["item_quantity"])
            item_cost = float(request.form["item_cost"])
            item_selling_price = float(request.form["item_selling_price"])
            item_color = request.form["item_color"].strip()
            item_size = request.form["item_size"].strip()
            profit = item_selling_price - item_cost  # Profit per item
            margin = ((item_selling_price - item_cost) /
                      item_selling_price) * 100  # Margin as a percentage

            inventory.append({
                "brand": item_brand,
                "name": item_name,
                "sku": item_sku,
                "quantity": item_quantity,
                "cost": item_cost,
                "selling_price": item_selling_price,
                "profit": profit,
                "margin": margin,
                "color": item_color,
                "size": item_size
            })

        # Update item quantity
        elif "update_item_index" in request.form and "new_quantity" in request.form:
            item_index = int(request.form["update_item_index"])
            new_quantity = int(request.form["new_quantity"])
            if 0 <= item_index < len(inventory):
                inventory[item_index]["quantity"] = new_quantity

        # Delete an inventory item
        elif "delete_item_index" in request.form:
            item_index = int(request.form["delete_item_index"])
            if 0 <= item_index < len(inventory):
                inventory.pop(item_index)

    # Calculate totals for display
    total_items_cost = sum(item["quantity"] * item["cost"]
                           for item in inventory)
    total_profit_available = sum(
        item["quantity"] * item["profit"] for item in inventory)
    total_revenue_available = sum(
        item["quantity"] * item["selling_price"] for item in inventory)

    # Corrected calculation for average inventory margin
    average_margin = (
        (total_profit_available / total_revenue_available) * 100
        if total_revenue_available > 0
        else 0
    )

    return render_template(
        "inventory.html",
        inventory=inventory,
        total_items_cost=total_items_cost,
        total_profit_available=total_profit_available,
        total_revenue_available=total_revenue_available,
        average_margin=average_margin
    )


@app.route("/init_db")
def init_db():
    db.create_all()  # Create all tables defined in the models
    return "Database initialized successfully!"


@app.route("/export_transactions", methods=["GET"])
def export_transactions():
    # Fetch all transactions from the database
    transactions = Transaction.query.all()

    # Prepare the data for export
    data = [
        {
            "Bank Name": transaction.bank.name,
            "Amount (BHD)": transaction.amount,
            "Description": transaction.description,
            "Timestamp": transaction.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        }
        for transaction in transactions
    ]

    # Create a DataFrame
    df = pd.DataFrame(data)

    # Export to CSV
    response = Response(
        df.to_csv(index=False),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=transactions.csv"}
    )
    return response


if __name__ == "__main__":
    app.run(debug=True, port=5111)
