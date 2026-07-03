// ---------------------------------------------------
// Book Bridge Platform - Client-side JavaScript
// ---------------------------------------------------

document.addEventListener("DOMContentLoaded", function () {

    // Simple client-side validation for the Add Book form
    const bookForm = document.getElementById("bookForm");

    if (bookForm) {
        bookForm.addEventListener("submit", function (event) {
            const requiredFields = bookForm.querySelectorAll("[required]");
            let isValid = true;

            requiredFields.forEach(function (field) {
                if (!field.value.trim()) {
                    isValid = false;
                    field.classList.add("is-invalid");
                } else {
                    field.classList.remove("is-invalid");
                }
            });

            if (!isValid) {
                event.preventDefault();
                alert("Please fill in all required fields before submitting.");
            }
        });

        // Remove the invalid highlight as soon as the user starts typing again
        bookForm.querySelectorAll("[required]").forEach(function (field) {
            field.addEventListener("input", function () {
                field.classList.remove("is-invalid");
            });
        });
    }

    // Auto-dismiss flash messages after 4 seconds
    const alerts = document.querySelectorAll(".alert");
    alerts.forEach(function (alert) {
        setTimeout(function () {
            alert.classList.remove("show");
            alert.classList.add("fade");
        }, 4000);
    });

});
