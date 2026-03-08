// Avukat AI — Chat JS

(function() {
    "use strict";

    // HTMX sonrasi: scroll en alta + input temizle
    document.addEventListener("htmx:afterSwap", function(event) {
        var chat = document.getElementById("chat-messages");
        if (chat) {
            chat.scrollTop = chat.scrollHeight;
        }
        var input = document.getElementById("chat-input");
        if (input) {
            input.value = "";
            input.focus();
        }
    });

    // Sayfa yuklendiginde scroll en alta
    window.addEventListener("load", function() {
        var chat = document.getElementById("chat-messages");
        if (chat) {
            chat.scrollTop = chat.scrollHeight;
        }
    });
})();
