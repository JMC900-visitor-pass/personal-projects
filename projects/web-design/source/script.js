// This file is loaded on every page. Each feature runs only where its HTML exists.
const countButton = document.getElementById('count-button');
if (countButton) {
  let count = 0;
  countButton.addEventListener('click', () => {
    count += 1;
    document.getElementById('count').textContent = count;
  });
}

const helloForm = document.getElementById('hello-form');
if (helloForm) {
  helloForm.addEventListener('submit', (event) => {
    event.preventDefault(); // Keep the browser on this page.
    const name = document.getElementById('visitor-name').value.trim();
    document.getElementById('form-result').textContent = `Hello, ${name}!`;
  });
}
