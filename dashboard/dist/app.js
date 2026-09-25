function setupDialog() {
  const dialog = document.querySelector('#details-dialog');
  const trigger = document.querySelector('#details-button');
  const close = document.querySelector('#close-dialog');
  if (!dialog || !trigger || !close) return;
  trigger.addEventListener('click', () => dialog.showModal());
  close.addEventListener('click', () => dialog.close());
}

setupDialog();
