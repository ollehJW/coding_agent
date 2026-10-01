// Save part of the page as an A4 PDF. The library is loaded only when someone downloads, to keep the app bundle small.
export async function savePdf(element, filename) {
  if (!element) throw new Error('PDF content is missing');
  // Snapshot before switching tabs removes the source content.
  const snapshot = element.cloneNode(true);
  const { default: html2pdf } = await import('html2pdf.js');
  await document.fonts.ready;
  await html2pdf().set({
    margin: [12, 10, 12, 10], filename,
    image: { type: 'jpeg', quality: 0.95 },
    html2canvas: { scale: 2, backgroundColor: '#ffffff', useCORS: true },
    jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
    pagebreak: { mode: ['css', 'legacy'], avoid: ['.history-step', '.history-branch', '.task-doc-section', '.task-doc-head'] },
  }).from(snapshot).save();
}

export function fileName(name, suffix, extension) {
  return `${name.replace(/[\\/:*?"<>|\x00-\x1f]/g, '_')}_${suffix}.${extension}`;
}
