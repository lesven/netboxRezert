(function () {
  "use strict";

  const token = window.RECERT_TOKEN;
  const submitBtn = document.getElementById("submit-btn");
  const selectAllCheckbox = document.getElementById("select-all");
  const bulkCount = document.getElementById("bulk-count");
  const bulkApplyBtn = document.getElementById("bulk-apply-btn");
  const bulkOwnerSearch = document.getElementById("bulk-owner-search");
  const bulkOwnerDropdown = document.getElementById("bulk-owner-dropdown");

  let bulkSelectedContact = null; // {id, name, email}

  function updateRowState(row) {
    const picker = row.querySelector(".owner-picker");
    const hidden = row.querySelector(".owner-value");
    const original = picker.dataset.original || "";
    const changed = hidden.value !== original;
    row.classList.toggle("changed", changed);
    updateSubmitState();
  }

  function updateSubmitState() {
    if (!submitBtn) return;
    const anyChanged = document.querySelectorAll(".vm-row.changed").length > 0;
    submitBtn.disabled = !anyChanged;
  }

  function closeDropdown(dropdown) {
    dropdown.hidden = true;
    dropdown.innerHTML = "";
  }

  function renderResults(dropdown, results, onPick) {
    dropdown.innerHTML = "";
    if (results.length === 0) {
      const empty = document.createElement("div");
      empty.className = "dropdown-empty";
      empty.textContent = "Keine Treffer";
      dropdown.appendChild(empty);
    } else {
      results.forEach((contact) => {
        const item = document.createElement("div");
        item.textContent = contact.email ? `${contact.name} (${contact.email})` : contact.name;
        item.addEventListener("mousedown", (e) => {
          // mousedown fires before the input's blur event, so the click isn't lost
          e.preventDefault();
          onPick(contact);
        });
        dropdown.appendChild(item);
      });
    }
    dropdown.hidden = false;
  }

  async function search(query) {
    const url = `/r/${encodeURIComponent(token)}/contacts/search?q=${encodeURIComponent(query)}`;
    const resp = await fetch(url);
    if (!resp.ok) {
      throw new Error(`Suche fehlgeschlagen (${resp.status})`);
    }
    const data = await resp.json();
    return data.results || [];
  }

  // Wires a text input + result dropdown into a live contact search.
  // onPick(contact) is called when the user picks a result; the dropdown is
  // closed automatically afterwards.
  function wireOwnerSearch(input, dropdown, onPick) {
    let debounceTimer = null;

    input.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      const query = input.value.trim();
      if (query.length < 2) {
        closeDropdown(dropdown);
        return;
      }
      debounceTimer = setTimeout(async () => {
        try {
          const results = await search(query);
          renderResults(dropdown, results, (contact) => {
            onPick(contact);
            closeDropdown(dropdown);
          });
        } catch (err) {
          dropdown.innerHTML = `<div class="dropdown-empty">${err.message}</div>`;
          dropdown.hidden = false;
        }
      }, 250);
    });

    input.addEventListener("blur", () => {
      setTimeout(() => closeDropdown(dropdown), 100);
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeDropdown(dropdown);
      } else if (e.key === "Enter") {
        // don't let Enter-in-search-box submit the surrounding form
        e.preventDefault();
      }
    });
  }

  function wireRow(row) {
    const input = row.querySelector(".owner-search");
    const dropdown = row.querySelector(".owner-dropdown");
    const hidden = row.querySelector(".owner-value");

    wireOwnerSearch(input, dropdown, (contact) => {
      input.value = contact.name;
      hidden.value = String(contact.id);
      updateRowState(row);
    });
  }

  // --- Bulk selection -------------------------------------------------

  function selectedRows() {
    return Array.from(document.querySelectorAll(".row-select:checked")).map((cb) =>
      cb.closest(".vm-row")
    );
  }

  function updateBulkToolbar() {
    const count = selectedRows().length;
    if (bulkCount) bulkCount.textContent = `${count} ausgewählt`;
    if (bulkApplyBtn) bulkApplyBtn.disabled = !(count > 0 && bulkSelectedContact);

    const allCheckboxes = document.querySelectorAll(".row-select");
    if (selectAllCheckbox && allCheckboxes.length > 0) {
      const checkedCount = document.querySelectorAll(".row-select:checked").length;
      selectAllCheckbox.checked = checkedCount === allCheckboxes.length;
      selectAllCheckbox.indeterminate = checkedCount > 0 && checkedCount < allCheckboxes.length;
    }
  }

  function wireBulkControls() {
    if (!bulkApplyBtn) return; // no VMs -> toolbar isn't rendered

    document.querySelectorAll(".row-select").forEach((cb) => {
      cb.addEventListener("change", updateBulkToolbar);
    });

    if (selectAllCheckbox) {
      selectAllCheckbox.addEventListener("change", () => {
        document.querySelectorAll(".row-select").forEach((cb) => {
          cb.checked = selectAllCheckbox.checked;
        });
        updateBulkToolbar();
      });
    }

    wireOwnerSearch(bulkOwnerSearch, bulkOwnerDropdown, (contact) => {
      bulkSelectedContact = contact;
      bulkOwnerSearch.value = contact.name;
      updateBulkToolbar();
    });

    bulkApplyBtn.addEventListener("click", () => {
      if (!bulkSelectedContact) return;
      selectedRows().forEach((row) => {
        const input = row.querySelector(".owner-search");
        const hidden = row.querySelector(".owner-value");
        input.value = bulkSelectedContact.name;
        hidden.value = String(bulkSelectedContact.id);
        updateRowState(row);
      });
    });

    updateBulkToolbar();
  }

  document.querySelectorAll(".vm-row").forEach((row) => {
    wireRow(row);
    updateRowState(row);
  });
  wireBulkControls();

  // --- Recertification (independent of the owner form above) ---------

  function wireRecertification() {
    const recertSubmitBtn = document.getElementById("recert-submit-btn");
    if (!recertSubmitBtn) return;

    function updateRecertState() {
      const anyTouched = document.querySelectorAll(".recert-select").length
        ? Array.from(document.querySelectorAll(".recert-select")).some((sel) => sel.value !== "")
        : false;
      recertSubmitBtn.disabled = !anyTouched;
    }

    document.querySelectorAll(".recert-select").forEach((select) => {
      select.addEventListener("change", () => {
        const row = select.closest(".recert-row");
        row.classList.toggle("changed", select.value !== "");
        updateRecertState();
      });
    });
  }

  wireRecertification();

  // --- Warn before leaving with unsaved changes -----------------------
  //
  // The owner form and the recert form are independent, but they live on
  // the same page: submitting one discards any unsaved state in the other
  // (it's a full navigation either way). So submitting a form only
  // suppresses the warning for *that* form's own changes, not the other
  // one's.

  let submittingFormId = null;

  const vmForm = document.getElementById("vm-form");
  if (vmForm) vmForm.addEventListener("submit", () => (submittingFormId = "vm-form"));

  const recertForm = document.getElementById("recert-form");
  if (recertForm) recertForm.addEventListener("submit", () => (submittingFormId = "recert-form"));

  function hasUnsavedChanges() {
    const ownerDirty =
      submittingFormId !== "vm-form" && document.querySelectorAll(".vm-row.changed").length > 0;
    const recertDirty =
      submittingFormId !== "recert-form" && document.querySelectorAll(".recert-row.changed").length > 0;
    return ownerDirty || recertDirty;
  }

  window.addEventListener("beforeunload", (e) => {
    if (!hasUnsavedChanges()) return;
    e.preventDefault();
    e.returnValue = ""; // required for the native "leave site?" prompt in most browsers
  });
})();
