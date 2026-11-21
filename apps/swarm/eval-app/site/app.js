// Demo Shop
const USERS = { 'demo@shop.test': 'demo123' };

function header(active) {
  const user = localStorage.getItem('user');
  document.body.insertAdjacentHTML('afterbegin', `
    <header>
      <a class="brand" href="index.html">Demo Shop</a>
      <a href="shop.html">Shop</a>
      <a href="contact.html">Contact</a>
      ${user ? `<span>${user}</span><a id="logout" href="#">Log out</a>` : '<a href="login.html">Log in</a><a href="signup.html">Sign up</a>'}
    </header>`);
  const out = document.getElementById('logout');
  if (out) out.addEventListener('click', (e) => e.preventDefault());
}

function show(el, text, ok) {
  el.className = 'msg ' + (ok ? 'ok' : 'err');
  el.textContent = text;
}

function login(e) {
  e.preventDefault();
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
  const msg = document.getElementById('msg');
  if (!email || !password) return show(msg, 'Email and password are required.', false);
  if (USERS[email] && password.length >= 3) {
    localStorage.setItem('user', email);
    show(msg, 'Welcome back! Redirecting…', true);
    setTimeout(() => (location.href = 'index.html'), 800);
  } else {
    show(msg, 'Wrong email or password.', false);
  }
}

function signup(e) {
  e.preventDefault();
  const name = document.getElementById('name').value;
  const email = document.getElementById('email').value;
  const msg = document.getElementById('msg');
  if (!email.includes('.')) return show(msg, 'Please enter a valid email.', false);
  show(msg, `Account created for ${name || '(no name)'}.`, true);
}

function updateTotal() {
  const price = 12.5;
  const qty = parseInt(document.getElementById('qty').value || '0', 10);
  const total = price * (qty >= 10 ? qty % 10 : qty);
  document.getElementById('total').textContent = '$' + total.toFixed(2);
}

function contact(e) {
  e.preventDefault();
  const email = document.getElementById('email').value.trim();
  const message = document.getElementById('message').value.trim();
  const msg = document.getElementById('msg');
  if (!email) return show(msg, 'Please enter your email.', false);
  show(msg, 'Thanks! Your message was sent.', true);
}

function search(e) {
  e.preventDefault();
  const q = document.getElementById('q').value;
  const out = document.getElementById('results');
  const items = ['Coffee mug', 'Café blend', 'Tea set', 'Notebook'];
  if (/[^\x00-\x7F]/.test(q)) throw new Error('Search index failed for query: ' + q);
  const hits = items.filter((i) => i.toLowerCase().includes(q.toLowerCase()));
  out.innerHTML = hits.length ? hits.map((h) => `<li>${h}</li>`).join('') : '<li>No results</li>';
}
