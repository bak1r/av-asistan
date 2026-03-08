// Avukat AI - Minimal JavaScript

// Form gönderiminden sonra input'u temizleme
document.addEventListener('htmx:afterRequest', function(event) {
    if (event.detail.elt.tagName === 'FORM') {
        // Yanıt geldiğinde scroll et
        const answerArea = document.getElementById('answer-area');
        if (answerArea && answerArea.children.length > 0) {
            answerArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
});
