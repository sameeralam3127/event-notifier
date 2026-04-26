// --- Utility ---
const api = (url, method = "GET", body = null) => {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  return fetch(url, opts).then((r) => {
    if (!r.ok)
      return r.text().then((t) => {
        throw new Error(t);
      });
    return r.json();
  });
};

// --- Validation ---
function validateEmail(email) {
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return re.test(email);
}

function validateSMTPConfig() {
  const host = document.getElementById("smtp_host").value.trim();
  const username = document.getElementById("smtp_user").value.trim();
  const password = document.getElementById("smtp_pass").value.trim();
  const fromEmail = document.getElementById("from_email").value.trim();

  if (!host) {
    showError("SMTP host is required");
    return false;
  }
  if (!username) {
    showError("Username is required");
    return false;
  }
  if (!password) {
    showError("Password is required");
    return false;
  }
  if (!fromEmail || !validateEmail(fromEmail)) {
    showError("Valid from email is required");
    return false;
  }
  return true;
}

function showError(message) {
  const toast = document.createElement("div");
  toast.className =
    "fixed top-4 right-4 bg-red-500 text-white px-6 py-3 rounded-lg shadow-lg z-50";
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

function showSuccess(message) {
  const toast = document.createElement("div");
  toast.className =
    "fixed top-4 right-4 bg-green-500 text-white px-6 py-3 rounded-lg shadow-lg z-50";
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

// --- Step navigation ---
function setActiveStep(step) {
  document.querySelectorAll(".step-item").forEach((el) => {
    const circle = el.querySelector(".step-circle");
    if (parseInt(el.dataset.step) <= step) {
      circle.classList.remove("bg-gray-300");
      circle.classList.add("bg-indigo-600");
    } else {
      circle.classList.remove("bg-indigo-600");
      circle.classList.add("bg-gray-300");
    }
  });
}

// --- Load saved SMTP config on page load ---
async function loadSavedSMTPConfig() {
  try {
    const config = await api("/api/get-smtp-config");
    if (config.host) {
      document.getElementById("smtp_host").value = config.host;
      document.getElementById("smtp_port").value = config.port;
      document.getElementById("smtp_user").value = config.username;
      document.getElementById("from_email").value = config.from_email;
      // Don't populate password for security
      document.getElementById("smtp-status").innerText = "✅ Config loaded";
      setActiveStep(2);
    }
  } catch (e) {
    console.log("No saved config found");
  }
}

// --- Load statistics ---
async function loadStatistics() {
  try {
    const stats = await api("/api/statistics");
    const statsDiv = document.getElementById("stats-display");
    if (stats.total_emails > 0) {
      statsDiv.innerHTML = `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div class="bg-blue-50 p-4 rounded-lg">
            <div class="text-2xl font-bold text-blue-600">${stats.total_emails}</div>
            <div class="text-sm text-gray-600">Total Emails</div>
          </div>
          <div class="bg-green-50 p-4 rounded-lg">
            <div class="text-2xl font-bold text-green-600">${stats.successful_emails}</div>
            <div class="text-sm text-gray-600">Successful</div>
          </div>
          <div class="bg-red-50 p-4 rounded-lg">
            <div class="text-2xl font-bold text-red-600">${stats.failed_emails}</div>
            <div class="text-sm text-gray-600">Failed</div>
          </div>
          <div class="bg-purple-50 p-4 rounded-lg">
            <div class="text-2xl font-bold text-purple-600">${stats.success_rate}%</div>
            <div class="text-sm text-gray-600">Success Rate</div>
          </div>
        </div>
      `;
      statsDiv.classList.remove("hidden");
    }
  } catch (e) {
    console.log("Failed to load statistics");
  }
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  loadSavedSMTPConfig();
  loadStatistics();
  setActiveStep(1);
});

// --- SMTP ---
document.getElementById("save-smtp").addEventListener("click", async () => {
  if (!validateSMTPConfig()) return;

  const config = {
    host: document.getElementById("smtp_host").value.trim(),
    port: parseInt(document.getElementById("smtp_port").value),
    username: document.getElementById("smtp_user").value.trim(),
    password: document.getElementById("smtp_pass").value.trim(),
    from_email: document.getElementById("from_email").value.trim(),
  };

  try {
    await api("/api/configure-smtp", "POST", config);
    document.getElementById("smtp-status").innerText = "✅ Saved";
    showSuccess("SMTP configuration saved successfully");
    setActiveStep(2);
  } catch (e) {
    showError("Failed to save SMTP: " + e.message);
  }
});

document.getElementById("test-smtp").addEventListener("click", async () => {
  if (!validateSMTPConfig()) return;

  // Save first
  const config = {
    host: document.getElementById("smtp_host").value.trim(),
    port: parseInt(document.getElementById("smtp_port").value),
    username: document.getElementById("smtp_user").value.trim(),
    password: document.getElementById("smtp_pass").value.trim(),
    from_email: document.getElementById("from_email").value.trim(),
  };

  await api("/api/configure-smtp", "POST", config);

  const btn = document.getElementById("test-smtp");
  btn.disabled = true;
  btn.innerText = "Testing...";
  const status = document.getElementById("smtp-status");

  try {
    const res = await api("/api/test-smtp", "POST");
    status.innerText = res.success ? "✅ " + res.message : "❌ " + res.message;
    if (res.success) {
      showSuccess(res.message);
    } else {
      showError(res.message);
    }
  } catch (e) {
    status.innerText = "❌ " + e.message;
    showError(e.message);
  } finally {
    btn.disabled = false;
    btn.innerText = "Test Connection";
  }
});

// --- Excel Upload ---
document.getElementById("excel-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  if (!file.name.endsWith(".xlsx") && !file.name.endsWith(".xls")) {
    showError("Please upload only .xlsx or .xls files");
    e.target.value = "";
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/upload-excel", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || "Upload failed");
    }

    const data = await res.json();
    showUploadPreview(data);
    populateColumnSelects(data.columns, data.guessed_name, data.guessed_email);
    document.getElementById("step3").classList.remove("hidden");
    document.getElementById("template-section").classList.add("hidden");
    showSuccess(`Loaded ${data.total_rows} rows successfully`);
    setActiveStep(3);
  } catch (e) {
    showError("Upload error: " + e.message);
    e.target.value = "";
  }
});

function showUploadPreview(data) {
  const previewDiv = document.getElementById("upload-preview");
  previewDiv.classList.remove("hidden");
  const table = document.getElementById("preview-table");
  let html = "<thead><tr>";
  data.columns.forEach(
    (col) =>
      (html += `<th class="p-2 border bg-gray-50 font-semibold">${col}</th>`),
  );
  html += "</tr></thead><tbody>";
  data.preview_rows.forEach((row) => {
    html += "<tr>";
    data.columns.forEach(
      (col) => (html += `<td class="p-2 border">${row[col] || ""}</td>`),
    );
    html += "</tr>";
  });
  html += "</tbody>";
  table.innerHTML = html;
  document.getElementById("row-count").innerText = data.total_rows;
}

function populateColumnSelects(columns, guessedName, guessedEmail) {
  const nameSel = document.getElementById("name-col-select");
  const emailSel = document.getElementById("email-col-select");
  [nameSel, emailSel].forEach((sel) => (sel.innerHTML = ""));
  columns.forEach((col) => {
    const opt = document.createElement("option");
    opt.value = col;
    opt.textContent = col;
    nameSel.appendChild(opt.cloneNode(true));
    emailSel.appendChild(opt.cloneNode(true));
  });
  if (guessedName) nameSel.value = guessedName;
  if (guessedEmail) emailSel.value = guessedEmail;
}

// --- Mapping ---
document.getElementById("save-mapping").addEventListener("click", async () => {
  const nameCol = document.getElementById("name-col-select").value;
  const emailCol = document.getElementById("email-col-select").value;

  if (!nameCol || !emailCol) {
    showError("Please select both name and email columns");
    return;
  }

  const mapping = {
    name_col: nameCol,
    email_col: emailCol,
  };

  try {
    await api("/api/set-mapping", "POST", mapping);
    document.getElementById("template-section").classList.remove("hidden");
    showSuccess("Column mapping saved");
  } catch (e) {
    showError("Mapping error: " + e.message);
  }
});

// --- Preview ---
document.getElementById("preview-btn").addEventListener("click", async () => {
  const subject = document.getElementById("subject-tpl").value.trim();
  const body = document.getElementById("body-tpl").value.trim();

  if (!subject || !body) {
    showError("Please enter both subject and body");
    return;
  }

  const tpl = { subject, body };

  try {
    const previews = await api("/api/preview", "POST", tpl);
    renderPreview(previews);
    document.getElementById("step4").classList.remove("hidden");
    document.getElementById("preview-container").classList.remove("hidden");
    document.getElementById("send-all").classList.remove("hidden");
    showSuccess("Preview generated successfully");
    setActiveStep(4);
  } catch (e) {
    showError("Preview failed: " + e.message);
  }
});

function renderPreview(previews) {
  const container = document.getElementById("preview-cards");
  container.innerHTML = previews
    .map(
      (p) => `
    <div class="border rounded-lg p-4 bg-gray-50 shadow-sm">
      <p class="mb-2"><strong>To:</strong> ${p.name} <${p.email}></p>
      <p class="mb-2"><strong>Subject:</strong> ${p.subject}</p>
      <div class="mt-2 p-3 bg-white border rounded">${p.body}</div>
    </div>
  `,
    )
    .join("");
}

// --- Send ---
document.getElementById("send-all").addEventListener("click", async () => {
  if (!confirm("Send emails to all recipients? This cannot be undone.")) return;

  const btn = document.getElementById("send-all");
  btn.disabled = true;
  btn.innerText = "Sending...";

  const tpl = {
    subject: document.getElementById("subject-tpl").value.trim(),
    body: document.getElementById("body-tpl").value.trim(),
  };

  try {
    const res = await api("/api/send-emails", "POST", tpl);
    showResults(res);
    showSuccess(`Sent ${res.success} emails successfully`);
    loadStatistics(); // Refresh statistics
  } catch (e) {
    showError("Sending failed: " + e.message);
  } finally {
    btn.disabled = false;
    btn.innerText = "Send to All";
  }
});

function showResults(data) {
  document.getElementById("results-container").classList.remove("hidden");
  const summary = document.getElementById("results-summary");
  summary.innerHTML = `
    <span class="px-4 py-2 bg-green-100 text-green-800 rounded-full font-semibold">✅ ${data.success} sent</span>
    <span class="px-4 py-2 bg-red-100 text-red-800 rounded-full font-semibold">❌ ${data.failed} failed</span>
    <span class="px-4 py-2 bg-blue-100 text-blue-800 rounded-full font-semibold">📊 Total: ${data.total}</span>
  `;

  const tbody = document.getElementById("results-table");
  tbody.innerHTML = data.results
    .map(
      (r) => `
    <tr class="hover:bg-gray-50">
      <td class="p-2 border">${r.email}</td>
      <td class="p-2 border">${r.name}</td>
      <td class="p-2 border">
        <span class="px-2 py-1 rounded text-xs font-semibold ${r.status === "success" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}">
          ${r.status}
        </span>
      </td>
      <td class="p-2 border text-sm text-red-600">${r.error || "-"}</td>
    </tr>
  `,
    )
    .join("");
}

// --- View History ---
document
  .getElementById("view-history-btn")
  ?.addEventListener("click", async () => {
    try {
      const history = await api("/api/email-history?limit=50");
      showHistoryModal(history.history);
    } catch (e) {
      showError("Failed to load history: " + e.message);
    }
  });

function showHistoryModal(history) {
  const modal = document.createElement("div");
  modal.className =
    "fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4";
  modal.innerHTML = `
    <div class="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[80vh] overflow-hidden">
      <div class="p-6 border-b flex justify-between items-center">
        <h3 class="text-xl font-semibold">Email History</h3>
        <button onclick="this.closest('.fixed').remove()" class="text-gray-500 hover:text-gray-700">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
        </button>
      </div>
      <div class="p-6 overflow-y-auto max-h-[60vh]">
        <table class="min-w-full text-sm">
          <thead class="bg-gray-50 sticky top-0">
            <tr>
              <th class="p-2 text-left">Date</th>
              <th class="p-2 text-left">Recipient</th>
              <th class="p-2 text-left">Subject</th>
              <th class="p-2 text-left">Status</th>
            </tr>
          </thead>
          <tbody>
            ${history
              .map(
                (h) => `
              <tr class="border-b hover:bg-gray-50">
                <td class="p-2">${new Date(h.sent_at).toLocaleString()}</td>
                <td class="p-2">${h.recipient_name} <${h.recipient_email}></td>
                <td class="p-2">${h.subject}</td>
                <td class="p-2">
                  <span class="px-2 py-1 rounded text-xs ${h.status === "success" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}">
                    ${h.status}
                  </span>
                </td>
              </tr>
            `,
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
}

// Made with Bob
