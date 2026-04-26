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
setActiveStep(1);

// --- SMTP ---
document.getElementById("save-smtp").addEventListener("click", async () => {
  const config = {
    host: document.getElementById("smtp_host").value,
    port: parseInt(document.getElementById("smtp_port").value),
    username: document.getElementById("smtp_user").value,
    password: document.getElementById("smtp_pass").value,
    from_email: document.getElementById("from_email").value,
  };
  try {
    await api("/api/configure-smtp", "POST", config);
    document.getElementById("smtp-status").innerText = "✅ Saved";
    setActiveStep(2);
  } catch (e) {
    alert("Failed to save SMTP: " + e.message);
  }
});

document.getElementById("test-smtp").addEventListener("click", async () => {
  const btn = document.getElementById("test-smtp");
  btn.disabled = true;
  btn.innerText = "Testing...";
  const status = document.getElementById("smtp-status");
  try {
    const res = await api("/api/test-smtp", "POST");
    status.innerText = res.success ? "✅ " + res.message : "❌ " + res.message;
  } catch (e) {
    status.innerText = "❌ " + e.message;
  } finally {
    btn.disabled = false;
    btn.innerText = "Test Connection";
  }
});

// --- Excel Upload ---
document.getElementById("excel-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch("/api/upload-excel", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    showUploadPreview(data);
    populateColumnSelects(data.columns, data.guessed_name, data.guessed_email);
    document.getElementById("step3").classList.remove("hidden");
    document.getElementById("template-section").classList.add("hidden");
    setActiveStep(3);
  } catch (e) {
    alert("Upload error: " + e.message);
  }
});

function showUploadPreview(data) {
  const previewDiv = document.getElementById("upload-preview");
  previewDiv.classList.remove("hidden");
  const table = document.getElementById("preview-table");
  let html = "<thead><tr>";
  data.columns.forEach((col) => (html += `<th class="p-2 border">${col}</th>`));
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
  const mapping = {
    name_col: document.getElementById("name-col-select").value,
    email_col: document.getElementById("email-col-select").value,
  };
  try {
    await api("/api/set-mapping", "POST", mapping);
    document.getElementById("template-section").classList.remove("hidden");
  } catch (e) {
    alert("Mapping error: " + e.message);
  }
});

// --- Preview ---
document.getElementById("preview-btn").addEventListener("click", async () => {
  const tpl = {
    subject: document.getElementById("subject-tpl").value,
    body: document.getElementById("body-tpl").value,
  };
  try {
    const previews = await api("/api/preview", "POST", tpl);
    renderPreview(previews);
    document.getElementById("step4").classList.remove("hidden");
    document.getElementById("preview-container").classList.remove("hidden");
    document.getElementById("send-all").classList.remove("hidden");
    setActiveStep(4);
  } catch (e) {
    alert("Preview failed: " + e.message);
  }
});

function renderPreview(previews) {
  const container = document.getElementById("preview-cards");
  container.innerHTML = previews
    .map(
      (p) => `
    <div class="border rounded p-4 bg-gray-50">
      <p><strong>To:</strong> ${p.name} &lt;${p.email}&gt;</p>
      <p><strong>Subject:</strong> ${p.subject}</p>
      <div class="mt-2 p-2 bg-white border rounded">${p.body}</div>
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
    subject: document.getElementById("subject-tpl").value,
    body: document.getElementById("body-tpl").value,
  };
  try {
    const res = await api("/api/send-emails", "POST", tpl);
    showResults(res);
  } catch (e) {
    alert("Sending failed: " + e.message);
  } finally {
    btn.disabled = false;
    btn.innerText = "Send to All";
  }
});

function showResults(data) {
  document.getElementById("results-container").classList.remove("hidden");
  const summary = document.getElementById("results-summary");
  summary.innerHTML = `
    <span class="px-3 py-1 bg-green-100 text-green-800 rounded-full">✅ ${data.success} sent</span>
    <span class="px-3 py-1 bg-red-100 text-red-800 rounded-full">❌ ${data.failed} failed</span>
  `;
  const tbody = document.getElementById("results-table");
  tbody.innerHTML = data.results
    .map(
      (r) => `
    <tr>
      <td class="p-2 border">${r.email}</td>
      <td class="p-2 border">${r.name}</td>
      <td class="p-2 border"><span class="text-${r.status === "success" ? "green" : "red"}-600 font-medium">${r.status}</span></td>
      <td class="p-2 border text-sm text-red-500">${r.error || ""}</td>
    </tr>
  `,
    )
    .join("");
}
