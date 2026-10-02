document.addEventListener('DOMContentLoaded', () => {
  const emptyBox = document.querySelector('.empty-state-box');
  if (emptyBox) {
    emptyBox.innerHTML = `
      <h2>No outreach campaign started yet.</h2>
      <p>Choose a set of potential buyers and send a structured business introduction from the buyer discovery workflow.</p>
      <a class="button button-primary" href="buyers.html">Start a Search</a>
    `;
  }
});
