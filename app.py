from flask import Flask, render_template, request, redirect, session, flash
from datetime import datetime, date, timedelta
import pyodbc
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_mmu_key'

def get_db_connection():
    return pyodbc.connect(
        'Driver={SQL Server};'
        'Server=PREDATOR-FAHMI\\MSSQLSERVER01;'
        'Database=LibraryDB;'
        'Trusted_Connection=yes;'
    )

@app.route('/')
def index():
    data = {}
    if 'user_id' in session:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if session['role'] == 'Admin':
            cursor.execute("""
                SELECT B.ID, B.Title, B.Genre, B.Status, 
                (SELECT TOP 1 U.Name FROM Loans L JOIN Users U ON L.UserID = U.ID WHERE L.BookID = B.ID ORDER BY L.ID DESC) as CurrentUser
                FROM Books B
            """)
            data['books'] = cursor.fetchall()
            
            cursor.execute("""
                SELECT 
                    U.ID, U.Name, U.Username, U.Role, U.Wallet,
                    (SELECT TOP 1 B.Title + ' (Borrowed: ' + FORMAT(L.BorrowDate, 'dd/MM') + ', Due: ' + FORMAT(L.DueDate, 'dd/MM') + ')' 
                     FROM Loans L JOIN Books B ON L.BookID = B.ID 
                     WHERE L.UserID = U.ID AND L.Status != 'Returned' 
                     ORDER BY L.BorrowDate DESC) as LoanInfo,
                    (SELECT COUNT(*) FROM Loans L 
                     WHERE L.UserID = U.ID 
                     AND L.ReturnDate IS NULL 
                     AND (L.DueDate < CAST(GETDATE() AS DATE) OR L.Status = 'Late' OR L.Fine > 0)) as PenaltyCount
                FROM Users U
            """)
            data['users'] = cursor.fetchall()

            cursor.execute("SELECT Value FROM Settings WHERE Name = 'LateFee'")
            data['penalty_rate'] = cursor.fetchone()[0]
            # Get borrow logs
            cursor.execute("""
                SELECT L.ID, U.Name as UserName, B.Title as BookTitle, L.BorrowDate, L.DueDate, L.Status 
                FROM Loans L 
                JOIN Users U ON L.UserID = U.ID 
                JOIN Books B ON L.BookID = B.ID
            """)
            data['logs'] = cursor.fetchall()
        else:
            # Member Data
            
            cursor.execute("SELECT ID, Title, Genre, Status FROM Books")
            data['books'] = cursor.fetchall()
            
            cursor.execute("SELECT Name, Email, Wallet FROM Users WHERE ID = ?", (session['user_id'],))
            data['user'] = cursor.fetchone()
            
            # Fetch the current penalty rate so we can calculate fines
            cursor.execute("SELECT Value FROM Settings WHERE Name = 'LateFee'")
            penalty_rate = cursor.fetchone()[0]
            
            # Get My Loans
            cursor.execute("""
                SELECT L.ID as LoanID, B.Title, L.DueDate, L.Status 
                FROM Loans L 
                JOIN Books B ON L.BookID = B.ID 
                WHERE L.UserID = ? AND L.Status != 'Returned'
            """, (session['user_id'],))
            raw_loans = cursor.fetchall()
            
            my_loans = []
            today = date.today() # Gets current date
            
            for loan in raw_loans:
                # Handle the date conversion safely
                if isinstance(loan.DueDate, str):
                    actual_date = datetime.strptime(loan.DueDate, '%Y-%m-%d').date()
                else:
                    # If PyODBC returns a datetime object, convert it to just a date
                    try:
                        actual_date = loan.DueDate.date()
                    except AttributeError:
                        actual_date = loan.DueDate
                        
                # 1. Format to Malaysia Date (DD/MM/YYYY)
                my_date_str = actual_date.strftime('%d/%m/%Y')
                
                # 2. Calculate if Late using the real-time clock
                days_late = (today - actual_date).days
                status = loan.Status
                fine = 0.00
                
                if days_late > 0:
                    status = 'Late'
                    fine = days_late * penalty_rate
                    
                my_loans.append({
                    'LoanID': loan.LoanID,
                    'Title': loan.Title,
                    'DueDate': my_date_str, 
                    'Status': status,
                    'Fine': fine
                })
                
            data['my_loans'] = my_loans
            
            # Get My Loans
            
            
        conn.close()
    return render_template('prototype.html', data=data)

# --- LOGIN / LOGOUT ---
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT ID, Username, Password, Role FROM Users WHERE Username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    
    # Check if user exists AND password is correct
    if user and user.Password == password:
        session['user_id'] = user.ID
        session['username'] = user.Username
        session['role'] = user.Role
        return redirect('/')
    else:
        # ERROR MESSAGE FOR LOGIN
        flash("The username or password is wrong!", "error")
        return redirect('/')

@app.route('/register', methods=['POST'])
def register():
    name = request.form['name']
    email = request.form['email']
    username = request.form['username']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Insert the new user. They are automatically a 'Member' with a 0.00 Wallet.
        cursor.execute("""
            INSERT INTO Users (Name, Email, Username, Password, Role, Wallet) 
            VALUES (?, ?, ?, ?, 'Member', 0.00)
        """, (name, email, username, password))
        conn.commit()
    except Exception as e:
        # If the username or email already exists, this prevents the app from crashing
        print("Registration Error:", e)
        
    conn.close()
    
    # Send them back to the login screen after registering
    return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# --- MEMBER FUNCTIONS ---
@app.route('/borrow', methods=['POST'])
def borrow():
    book_id = request.form['book_id']
    due_date = request.form['due_date'] # Gets date from your original prototype's date picker
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO Loans (UserID, BookID, DueDate, Status) VALUES (?, ?, ?, 'Active')", 
                   (user_id, book_id, due_date))
    cursor.execute("UPDATE Books SET Status = 'Borrowed' WHERE ID = ?", (book_id,))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/return_book', methods=['POST'])
def return_book():
    loan_id = request.form['loan_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    # Find which book was returned
    cursor.execute("SELECT BookID FROM Loans WHERE ID = ?", (loan_id,))
    book_id = cursor.fetchone()[0]
    
    cursor.execute("UPDATE Loans SET Status = 'Returned', ReturnDate = GETDATE() WHERE ID = ?", (loan_id,))
    cursor.execute("UPDATE Books SET Status = 'Available' WHERE ID = ?", (book_id,))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/pay_penalty', methods=['POST'])
def pay_penalty():
    loan_id = request.form['loan_id']
    fine_amount = float(request.form['fine_amount'])
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if user has enough money in their wallet
    cursor.execute("SELECT Wallet FROM Users WHERE ID = ?", (user_id,))
    wallet = cursor.fetchone()[0]
    
    if wallet >= fine_amount:
        # Deduct money from wallet
        cursor.execute("UPDATE Users SET Wallet = Wallet - ? WHERE ID = ?", (fine_amount, user_id))
        
        # Get BookID to make it available again
        cursor.execute("SELECT BookID FROM Loans WHERE ID = ?", (loan_id,))
        book_id = cursor.fetchone()[0]
        
        # Mark as returned and record the fine paid
        cursor.execute("UPDATE Loans SET Status = 'Returned', ReturnDate = GETDATE(), Fine = ? WHERE ID = ?", (fine_amount, loan_id))
        cursor.execute("UPDATE Books SET Status = 'Available' WHERE ID = ?", (book_id,))
        
        conn.commit()
    else:
        # If they don't have enough money, you could add an error message here later
        print("Not enough money in wallet!")
        
    conn.close()
    return redirect('/')

@app.route('/reload', methods=['POST'])
def reload():
    amount = float(request.form['amount'])
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Users SET Wallet = Wallet + ? WHERE ID = ?", (amount, session['user_id']))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return redirect('/login')

    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']

    if new_password != confirm_password:
        flash("Error: New passwords do not match!", "error")
        return redirect('/') 

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT Password FROM Users WHERE ID = ?", (session['user_id'],))
    user = cursor.fetchone()

    if user and user.Password == current_password:
        cursor.execute("UPDATE Users SET Password = ? WHERE ID = ?", (new_password, session['user_id']))
        conn.commit()
        flash("Success: Password updated successfully!", "success")
    else:
        # ERROR MESSAGE FOR CHANGE PASSWORD
        flash("The current password is wrong!", "error")

    conn.close()
    return redirect('/')

# --- ADMIN FUNCTIONS ---
@app.route('/add_book', methods=['POST'])
def add_book():
    title = request.form['title']
    genre = request.form['genre'] # Grab the new input
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # Insert both title and genre into the database
    cursor.execute("INSERT INTO Books (Title, Genre, Status) VALUES (?, ?, 'Available')", (title, genre))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/edit_book', methods=['POST'])
def edit_book():
    # Make sure only admins can edit!
    if session.get('role') != 'Admin':
        return redirect('/')

    book_id = request.form['book_id']
    new_title = request.form['new_title']
    new_genre = request.form['new_genre']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # Update both the Title and Genre for the specific book
    cursor.execute("UPDATE Books SET Title = ?, Genre = ? WHERE ID = ?", (new_title, new_genre, book_id))
    conn.commit()
    conn.close()
    
    return redirect('/')

@app.route('/delete_book', methods=['POST'])
def delete_book():
    if session.get('role') != 'Admin':
        return redirect('/')

    book_id = request.form['book_id']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # STEP 1: Delete all loan history for this book first
        # This removes the "links" you see in your screenshot
        cursor.execute("DELETE FROM Loans WHERE BookID = ?", (book_id,))
        
        # STEP 2: Now that the history is gone, delete the book itself
        cursor.execute("DELETE FROM Books WHERE ID = ?", (book_id,))
        
        conn.commit()
        flash("Book and its loan history deleted successfully!", "success")
    except Exception as e:
        conn.rollback() # Undo changes if something goes wrong
        flash("Error: System failed to delete the book.", "error")
        print(e)
        
    conn.close()
    return redirect('/')

@app.route('/update_penalty', methods=['POST'])
def update_penalty():
    new_rate = request.form['rate']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Settings SET Value = ? WHERE Name = 'LateFee'", (new_rate,))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/delete_user', methods=['POST'])
def delete_user():
    if session.get('role') != 'Admin':
        return redirect('/')

    target_id = request.form['user_id']
    
    # Safety Check: Don't let an Admin delete themselves!
    if int(target_id) == session.get('user_id'):
        flash("Error: You cannot delete your own account!", "error")
        return redirect('/')

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Step 1: Clear user's loan history first to avoid FK errors
        cursor.execute("DELETE FROM Loans WHERE UserID = ?", (target_id,))
        # Step 2: Delete the user
        cursor.execute("DELETE FROM Users WHERE ID = ?", (target_id,))
        conn.commit()
        flash("User and their history deleted successfully!", "success")
    except Exception as e:
        conn.rollback()
        flash("Error: Could not delete user.", "error")
        print(e)
        
    conn.close()
    return redirect('/')

@app.route('/set_role', methods=['POST'])
def set_role():
    if session.get('role') != 'Admin':
        return redirect('/')

    target_id = request.form['user_id']
    new_role = request.form['new_role']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Users SET Role = ? WHERE ID = ?", (new_role, target_id))
    conn.commit()
    conn.close()
    
    flash(f"User role updated to {new_role}!", "success")
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)