function extractArticleText() {
  // Try to find the main article container
  const article = document.querySelector('article') || document.querySelector('.post-content') || document.querySelector('.entry-content');
  
  if (article) {
    return article.innerText;
  }
  
  // Fallback: grab all paragraphs
  const paragraphs = Array.from(document.querySelectorAll('p'));
  const text = paragraphs.map(p => p.innerText).join('\n');
  return text;
}

// Ensure the function is available to execute via scripting
extractArticleText();
