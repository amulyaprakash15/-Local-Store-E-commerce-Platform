from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['UPLOAD_FOLDER'] = 'static/images'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Database setup
def init_db():
    conn = sqlite3.connect('store.db')
    c = conn.cursor()
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  description TEXT,
                  price REAL NOT NULL,
                  image TEXT,
                  stock INTEGER DEFAULT 10,
                  category TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  email TEXT,
                  address TEXT,
                  phone TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  order_date TEXT NOT NULL,
                  status TEXT DEFAULT 'Processing',
                  total REAL NOT NULL,
                  payment_method TEXT,
                  shipping_address TEXT,
                  FOREIGN KEY (user_id) REFERENCES users(id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS order_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  order_id INTEGER NOT NULL,
                  product_id INTEGER NOT NULL,
                  quantity INTEGER NOT NULL,
                  price REAL NOT NULL,
                  FOREIGN KEY (order_id) REFERENCES orders(id),
                  FOREIGN KEY (product_id) REFERENCES products(id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS reviews
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  product_id INTEGER NOT NULL,
                  user_id INTEGER NOT NULL,
                  rating INTEGER NOT NULL,
                  comment TEXT,
                  review_date TEXT NOT NULL,
                  FOREIGN KEY (product_id) REFERENCES products(id),
                  FOREIGN KEY (user_id) REFERENCES users(id))''')
    
    # Insert sample products if none exist
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        sample_products = [
            ("Apple", "Fresh red apples from local farms", 1.99, "apple.jpg", 50, "Fruits"),
            ("Banana", "Organic yellow bananas", 0.99, "banana.jpg", 100, "Fruits"),
            ("Milk", "1 liter of fresh whole milk", 2.49, "milk.jpg", 30, "Dairy"),
            ("Bread", "Whole wheat bread baked daily", 1.79, "bread.jpg", 40, "Bakery"),
            ("Eggs", "Dozen of free-range eggs", 3.49, "eggs.jpg", 25, "Dairy"),
            ("Chicken", "Fresh whole chicken", 5.99, "chicken.jpg", 15, "Meat"),
            ("Tomato", "Vine-ripened tomatoes", 2.29, "tomato.jpg", 60, "Vegetables"),
            ("Potato", "Russet potatoes 5lb bag", 3.99, "potato.jpg", 35, "Vegetables")
        ]
        c.executemany("INSERT INTO products (name, description, price, image, stock, category) VALUES (?, ?, ?, ?, ?, ?)", sample_products)
    
    conn.commit()
    conn.close()

init_db()

# Helper functions
def get_db():
    conn = sqlite3.connect('store.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_cart():
    return session.get('cart', {})

def calculate_cart_total():
    cart = get_cart()
    total = 0
    conn = get_db()
    c = conn.cursor()
    
    for product_id, quantity in cart.items():
        c.execute("SELECT price FROM products WHERE id = ?", (product_id,))
        product = c.fetchone()
        if product:
            total += product['price'] * quantity
    
    conn.close()
    return round(total, 2)

def get_cart_items():
    cart = get_cart()
    items = []
    if cart:
        conn = get_db()
        c = conn.cursor()
        product_ids = list(cart.keys())
        query = "SELECT * FROM products WHERE id IN ({})".format(','.join(['?']*len(product_ids)))
        c.execute(query, product_ids)
        products = c.fetchall()
        for product in products:
            items.append({
                'id': product['id'],
                'name': product['name'],
                'price': product['price'],
                'image': product['image'],
                'quantity': cart[str(product['id'])],
                'subtotal': product['price'] * cart[str(product['id'])]
            })
        conn.close()
    return items

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Routes
@app.route('/')
def home():
    conn = get_db()
    c = conn.cursor()
    
    category = request.args.get('category')
    search = request.args.get('search')
    sort = request.args.get('sort', 'name')
    min_price = request.args.get('min_price')
    max_price = request.args.get('max_price')
    
    query = "SELECT * FROM products WHERE 1=1"
    params = []
    
    if category and category != 'all':
        query += " AND category = ?"
        params.append(category)
    
    if search:
        query += " AND (name LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    
    if min_price:
        query += " AND price >= ?"
        params.append(float(min_price))
    
    if max_price:
        query += " AND price <= ?"
        params.append(float(max_price))
    
    if sort == 'price_asc':
        query += " ORDER BY price ASC"
    elif sort == 'price_desc':
        query += " ORDER BY price DESC"
    elif sort == 'newest':
        query += " ORDER BY id DESC"
    else:
        query += " ORDER BY name"
    
    c.execute(query, params)
    products = c.fetchall()
    
    c.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL")
    categories = [row['category'] for row in c.fetchall()]
    
    conn.close()
    
    return render_template('home.html', 
                         products=products, 
                         categories=categories,
                         cart_size=len(get_cart()))

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = c.fetchone()
    
    if not product:
        flash('Product not found', 'error')
        return redirect(url_for('home'))
    
    c.execute('''SELECT reviews.*, users.username 
                 FROM reviews 
                 JOIN users ON reviews.user_id = users.id 
                 WHERE product_id = ? 
                 ORDER BY review_date DESC''', (product_id,))
    reviews = c.fetchall()
    
    c.execute("SELECT AVG(rating) FROM reviews WHERE product_id = ?", (product_id,))
    avg_rating = c.fetchone()[0] or 0
    
    conn.close()
    
    return render_template('product_detail.html', 
                         product=product, 
                         reviews=reviews, 
                         avg_rating=round(avg_rating, 1),
                         cart_size=len(get_cart()))

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    quantity = int(request.form.get('quantity', 1))
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
    stock = c.fetchone()[0]
    conn.close()
    
    cart = get_cart()
    current_quantity = cart.get(str(product_id), 0)
    
    if current_quantity + quantity > stock:
        flash(f'Only {stock} available in stock', 'error')
        return redirect(request.referrer or url_for('home'))
    
    cart[str(product_id)] = current_quantity + quantity
    session['cart'] = cart
    
    flash('Product added to cart', 'success')
    return redirect(request.referrer or url_for('home'))

@app.route('/update_cart/<int:product_id>', methods=['POST'])
def update_cart(product_id):
    quantity = int(request.form.get('quantity', 1))
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
    stock = c.fetchone()[0]
    conn.close()
    
    if quantity > stock:
        flash(f'Only {stock} available in stock', 'error')
        return redirect(url_for('view_cart'))
    
    cart = get_cart()
    if quantity <= 0:
        cart.pop(str(product_id), None)
    else:
        cart[str(product_id)] = quantity
    session['cart'] = cart
    
    flash('Cart updated', 'success')
    return redirect(url_for('view_cart'))

@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    cart = get_cart()
    cart.pop(str(product_id), None)
    session['cart'] = cart
    
    flash('Product removed from cart', 'success')
    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    items = get_cart_items()
    total = sum(item['subtotal'] for item in items)
    
    return render_template('cart.html', 
                         items=items, 
                         total=round(total, 2),
                         cart_size=len(get_cart()))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        flash('Please login to checkout', 'error')
        return redirect(url_for('login', next=url_for('checkout')))
    
    cart = get_cart()
    if not cart:
        flash('Your cart is empty', 'error')
        return redirect(url_for('home'))
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
    user = c.fetchone()
    conn.close()
    
    if request.method == 'POST':
        payment_method = request.form.get('payment_method')
        shipping_address = request.form.get('shipping_address', user['address'])
        
        if not payment_method:
            flash('Please select a payment method', 'error')
            return redirect(url_for('checkout'))
        
        conn = get_db()
        c = conn.cursor()
        
        try:
            # Check stock before processing order
            for product_id, quantity in cart.items():
                c.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
                stock = c.fetchone()[0]
                if quantity > stock:
                    flash(f'Not enough stock for {product_id}', 'error')
                    return redirect(url_for('checkout'))
            
            # Create order
            total = calculate_cart_total()
            order_date = datetime.now().isoformat()
            c.execute('''INSERT INTO orders 
                         (user_id, order_date, total, payment_method, shipping_address) 
                         VALUES (?, ?, ?, ?, ?)''',
                      (session['user_id'], order_date, total, payment_method, shipping_address))
            order_id = c.lastrowid
            
            # Add order items and update stock
            for product_id, quantity in cart.items():
                c.execute("SELECT price FROM products WHERE id = ?", (product_id,))
                price = c.fetchone()[0]
                c.execute('''INSERT INTO order_items 
                            (order_id, product_id, quantity, price) 
                            VALUES (?, ?, ?, ?)''',
                          (order_id, product_id, quantity, price))
                c.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (quantity, product_id))
            
            # Clear cart
            session.pop('cart', None)
            
            conn.commit()
            flash('Order placed successfully!', 'success')
            return redirect(url_for('order_confirmation', order_id=order_id))
        except Exception as e:
            conn.rollback()
            flash('Error processing your order. Please try again.', 'error')
            return redirect(url_for('checkout'))
        finally:
            conn.close()
    
    return render_template('checkout.html', 
                         total=calculate_cart_total(),
                         user=user,
                         cart_size=len(get_cart()))

@app.route('/order_confirmation/<int:order_id>')
def order_confirmation(order_id):
    if 'user_id' not in session:
        flash('Please login to view this page', 'error')
        return redirect(url_for('login'))
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''SELECT o.*, 
                 COUNT(oi.id) as item_count 
                 FROM orders o 
                 JOIN order_items oi ON o.id = oi.order_id 
                 WHERE o.id = ? AND o.user_id = ?
                 GROUP BY o.id''', (order_id, session['user_id']))
    order = c.fetchone()
    
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('home'))
    
    c.execute('''SELECT oi.*, p.name, p.image 
                 FROM order_items oi 
                 JOIN products p ON oi.product_id = p.id 
                 WHERE oi.order_id = ?''', (order_id,))
    items = c.fetchall()
    
    conn.close()
    
    return render_template('order_confirmation.html', 
                         order=order, 
                         items=items,
                         cart_size=len(get_cart()))

@app.route('/orders')
def view_orders():
    if 'user_id' not in session:
        flash('Please login to view your orders', 'error')
        return redirect(url_for('login'))
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''SELECT o.*, 
                 COUNT(oi.id) as item_count 
                 FROM orders o 
                 JOIN order_items oi ON o.id = oi.order_id 
                 WHERE o.user_id = ? 
                 GROUP BY o.id 
                 ORDER BY o.order_date DESC''', (session['user_id'],))
    orders = c.fetchall()
    
    conn.close()
    
    return render_template('orders.html', 
                         orders=orders,
                         cart_size=len(get_cart()))

@app.route('/order/<int:order_id>')
def order_detail(order_id):
    if 'user_id' not in session:
        flash('Please login to view this page', 'error')
        return redirect(url_for('login'))
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''SELECT o.* 
                 FROM orders o 
                 WHERE o.id = ? AND o.user_id = ?''', (order_id, session['user_id']))
    order = c.fetchone()
    
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('home'))
    
    c.execute('''SELECT oi.*, p.name, p.image, p.id as product_id 
                 FROM order_items oi 
                 JOIN products p ON oi.product_id = p.id 
                 WHERE oi.order_id = ?''', (order_id,))
    items = c.fetchall()
    
    conn.close()
    
    return render_template('order_detail.html', 
                         order=order, 
                         items=items,
                         cart_size=len(get_cart()))

@app.route('/add_review/<int:product_id>', methods=['POST'])
def add_review(product_id):
    if 'user_id' not in session:
        flash('Please login to leave a review', 'error')
        return redirect(url_for('login'))
    
    rating = int(request.form.get('rating'))
    comment = request.form.get('comment', '').strip()
    
    if not 1 <= rating <= 5:
        flash('Invalid rating', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    
    conn = get_db()
    c = conn.cursor()
    
    try:
        # Check if user has purchased this product
        c.execute('''SELECT 1 FROM order_items oi
                     JOIN orders o ON oi.order_id = o.id
                     WHERE o.user_id = ? AND oi.product_id = ?''',
                  (session['user_id'], product_id))
        if not c.fetchone():
            flash('You need to purchase this product before reviewing', 'error')
            return redirect(url_for('product_detail', product_id=product_id))
        
        # Check if user already reviewed this product
        c.execute('''SELECT 1 FROM reviews 
                     WHERE user_id = ? AND product_id = ?''',
                  (session['user_id'], product_id))
        if c.fetchone():
            flash('You have already reviewed this product', 'error')
            return redirect(url_for('product_detail', product_id=product_id))
        
        # Add review
        review_date = datetime.now().isoformat()
        c.execute('''INSERT INTO reviews 
                     (product_id, user_id, rating, comment, review_date)
                     VALUES (?, ?, ?, ?, ?)''',
                  (product_id, session['user_id'], rating, comment, review_date))
        
        conn.commit()
        flash('Review added successfully', 'success')
    except Exception as e:
        conn.rollback()
        flash('Error adding review', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        address = request.form.get('address')
        phone = request.form.get('phone')
        
        if not username or not password:
            flash('Username and password are required', 'error')
            return redirect(url_for('register'))
        
        conn = get_db()
        c = conn.cursor()
        
        try:
            hashed_password = generate_password_hash(password)
            c.execute('''INSERT INTO users 
                        (username, password, email, address, phone) 
                        VALUES (?, ?, ?, ?, ?)''',
                      (username, hashed_password, email, address, phone))
            conn.commit()
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
        finally:
            conn.close()
    
    return render_template('register.html', cart_size=len(get_cart()))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db()
        c = conn.cursor()
        
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login successful', 'success')
            
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home'))
        else:
            flash('Invalid username or password', 'error')
            return redirect(url_for('login'))
    
    return render_template('login.html', cart_size=len(get_cart()))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('home'))

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        
        # In a real app, you would send an email or save this to a database
        flash('Thank you for your message! We will get back to you soon.', 'success')
        return redirect(url_for('contact'))
    
    return render_template('contact.html', cart_size=len(get_cart()))

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        flash('Image uploaded successfully', 'success')
        return redirect(url_for('home'))
    return redirect(request.url)

@app.route('/static/images/<filename>')
def serve_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Context processor to make categories available in all templates
@app.context_processor
def inject_categories():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL")
    categories = [row['category'] for row in c.fetchall()]
    conn.close()
    return dict(categories=categories)

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/images', exist_ok=True)
    
    # Run the app
    app.run(debug=True)