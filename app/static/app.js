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
    const badge = row.querySelector(".changed-badge");
    const original = picker.dataset.original || "";
    const changed = hidden.value !== original;
    row.classList.toggle("changed", changed);
    // The yellow row background alone doesn't convey "changed" to color-blind
    // users or screen readers - the badge carries the same info as text.
    if (badge) badge.hidden = !changed;
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
    dropdown.activeIndex = -1;
    dropdown._results = null;
    const input = dropdown._input;
    if (input) {
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    }
  }

  // Highlights the option at `index` (keyboard arrow navigation) and keeps
  // aria-activedescendant on the owning input in sync for screen readers.
  function setActiveOption(dropdown, index) {
    const items = Array.from(dropdown.querySelectorAll('[role="option"]'));
    items.forEach((el, i) => el.classList.toggle("active", i === index));
    dropdown.activeIndex = index;
    const activeEl = items[index];
    const input = dropdown._input;
    if (input) {
      if (activeEl) {
        input.setAttribute("aria-activedescendant", activeEl.id);
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }
    if (activeEl && activeEl.scrollIntoView) activeEl.scrollIntoView({ block: "nearest" });
  }

  function renderResults(input, dropdown, results, onPick) {
    dropdown.innerHTML = "";
    dropdown._results = results;
    dropdown.activeIndex = -1;
    if (results.length === 0) {
      const empty = document.createElement("div");
      empty.className = "dropdown-empty";
      empty.textContent = "Keine Treffer";
      dropdown.appendChild(empty);
    } else {
      results.forEach((contact, i) => {
        const item = document.createElement("div");
        item.id = `${dropdown.id}-opt-${i}`;
        item.setAttribute("role", "option");
        item.textContent = contact.email ? `${contact.name} (${contact.email})` : contact.name;
        item.addEventListener("mousedown", (e) => {
          // mousedown fires before the input's blur event, so the click isn't lost
          e.preventDefault();
          onPick(contact);
        });
        item.addEventListener("mousemove", () => setActiveOption(dropdown, i));
        dropdown.appendChild(item);
      });
    }
    dropdown.hidden = false;
    input.setAttribute("aria-expanded", "true");
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
  //
  // getConfirmedName, if given, guards against a "false" state: if the user
  // types a name but blurs without actually picking a suggestion (e.g.
  // clicks away, tabs out), the input text would otherwise keep showing a
  // name that was never actually selected/saved anywhere. On blur we reset
  // the visible text back to the last confirmed value so what's displayed
  // always matches what's actually stored in the hidden field.
  function wireOwnerSearch(input, dropdown, onPick, getConfirmedName) {
    let debounceTimer = null;
    dropdown._input = input;

    const pickAndClose = (contact) => {
      onPick(contact);
      closeDropdown(dropdown);
    };

    input.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      const query = input.value.trim();
      if (query.length < 2) {
        closeDropdown(dropdown);
        return;
      }
      // Show a loading placeholder immediately so a slow NetBox lookup
      // doesn't look like the search silently did nothing. _results is
      // cleared too, so Enter can't act on a stale previous result set
      // while this placeholder is showing.
      dropdown.innerHTML = '<div class="dropdown-loading">Suche…</div>';
      dropdown.hidden = false;
      dropdown._results = null;
      dropdown.activeIndex = -1;
      input.setAttribute("aria-expanded", "true");
      debounceTimer = setTimeout(async () => {
        try {
          const results = await search(query);
          renderResults(input, dropdown, results, pickAndClose);
        } catch (err) {
          dropdown.innerHTML = `<div class="dropdown-empty">${err.message}</div>`;
          dropdown.hidden = false;
        }
      }, 250);
    });

    input.addEventListener("blur", () => {
      setTimeout(() => {
        closeDropdown(dropdown);
        if (getConfirmedName) {
          const confirmed = getConfirmedName();
          if (input.value !== confirmed) {
            input.value = confirmed;
          }
        }
      }, 100);
    });

    input.addEventListener("keydown", (e) => {
      const hasResults = !dropdown.hidden && dropdown._results && dropdown._results.length > 0;
      if (e.key === "ArrowDown") {
        if (!hasResults) return;
        e.preventDefault();
        const next = dropdown.activeIndex < 0 ? 0 : Math.min(dropdown.activeIndex + 1, dropdown._results.length - 1);
        setActiveOption(dropdown, next);
      } else if (e.key === "ArrowUp") {
        if (!hasResults) return;
        e.preventDefault();
        const prev = dropdown.activeIndex < 0 ? 0 : Math.max(dropdown.activeIndex - 1, 0);
        setActiveOption(dropdown, prev);
      } else if (e.key === "Escape") {
        closeDropdown(dropdown);
      } else if (e.key === "Enter") {
        // don't let Enter-in-search-box submit the surrounding form
        e.preventDefault();
        if (!hasResults) return;
        const idx = dropdown.activeIndex < 0 ? 0 : dropdown.activeIndex;
        pickAndClose(dropdown._results[idx]);
      }
    });
  }

  function wireRow(row) {
    const input = row.querySelector(".owner-search");
    const dropdown = row.querySelector(".owner-dropdown");
    const hidden = row.querySelector(".owner-value");
    let confirmedName = input.value;

    wireOwnerSearch(
      input,
      dropdown,
      (contact) => {
        input.value = contact.name;
        confirmedName = contact.name;
        hidden.value = String(contact.id);
        updateRowState(row);
      },
      () => confirmedName
    );
  }

  // --- Bulk selection -------------------------------------------------

  function isRowVisible(row) {
    return !!row && !row.classList.contains("filtered-out");
  }

  function selectedRows() {
    return Array.from(document.querySelectorAll(".row-select:checked")).map((cb) =>
      cb.closest(".vm-row")
    );
  }

  function updateBulkToolbar() {
    const count = selectedRows().length;
    if (bulkCount) bulkCount.textContent = `${count} ausgewählt`;
    if (bulkApplyBtn) bulkApplyBtn.disabled = !(count > 0 && bulkSelectedContact);

    // "Select all" only reflects/affects rows the current filter shows -
    // otherwise checking it would silently also select VMs the user can't
    // even see right now.
    if (selectAllCheckbox) {
      const visibleCheckboxes = Array.from(document.querySelectorAll(".row-select")).filter((cb) =>
        isRowVisible(cb.closest(".vm-row"))
      );
      const checkedVisible = visibleCheckboxes.filter((cb) => cb.checked).length;
      selectAllCheckbox.checked = visibleCheckboxes.length > 0 && checkedVisible === visibleCheckboxes.length;
      selectAllCheckbox.indeterminate = checkedVisible > 0 && checkedVisible < visibleCheckboxes.length;
    }
  }

  function wireBulkControls() {
    if (!bulkApplyBtn) return; // no VMs -> toolbar isn't rendered

    document.querySelectorAll(".row-select").forEach((cb) => {
      cb.addEventListener("change", updateBulkToolbar);
    });

    if (selectAllCheckbox) {
      selectAllCheckbox.addEventListener("change", () => {
        document.querySelectorAll(".vm-row").forEach((row) => {
          if (!isRowVisible(row)) return;
          const cb = row.querySelector(".row-select");
          if (cb) cb.checked = selectAllCheckbox.checked;
        });
        updateBulkToolbar();
      });
    }

    wireOwnerSearch(
      bulkOwnerSearch,
      bulkOwnerDropdown,
      (contact) => {
        bulkSelectedContact = contact;
        bulkOwnerSearch.value = contact.name;
        updateBulkToolbar();
      },
      () => (bulkSelectedContact ? bulkSelectedContact.name : "")
    );

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

  // --- VM name filter (applies to both tables at once) -----------------

  function wireVmFilter() {
    const filterInput = document.getElementById("vm-filter");
    if (!filterInput) return;
    const rows = document.querySelectorAll(".vm-row, .recert-row");

    filterInput.addEventListener("input", () => {
      const query = filterInput.value.trim().toLowerCase();
      rows.forEach((row) => {
        const matches = !query || (row.dataset.vmName || "").includes(query);
        row.classList.toggle("filtered-out", !matches);
      });
      updateBulkToolbar();
    });
  }

  document.querySelectorAll(".vm-row").forEach((row) => {
    wireRow(row);
    updateRowState(row);
  });
  wireBulkControls();
  wireVmFilter();

  // --- Section nav: highlight which section is currently in view -------
  //
  // The nav itself is sticky (CSS), but that alone doesn't show *which* of
  // the two sections you're currently scrolled through. Watching the two
  // section headings and toggling .active on the matching nav link keeps
  // that "there are two sections, you're in #1 right now" context visible
  // even without reading the URL hash.

  function wireSectionNavHighlight() {
    const nav = document.querySelector(".section-nav");
    if (!nav || !window.IntersectionObserver) return;

    const sections = Array.from(document.querySelectorAll("#owner-section, #recert-section"));
    if (sections.length === 0) return;

    const linkFor = (id) => nav.querySelector(`a[href="#${id}"]`);

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const link = linkFor(entry.target.id);
          if (!link) return;
          nav.querySelectorAll("a.active").forEach((a) => a.classList.remove("active"));
          link.classList.add("active");
        });
      },
      // Counts a section as "current" once its heading has scrolled just
      // past the sticky nav, rather than only right at the very top.
      { rootMargin: "-56px 0px -85% 0px" }
    );

    sections.forEach((section) => observer.observe(section));
  }

  wireSectionNavHighlight();

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

    // A comment is only ever written together with an explicit ja/nein choice
    // (see app/routers/owner.py) - editing just the comment and leaving the
    // select on "nicht bearbeitet" silently drops that comment on save. Flag
    // that state inline per row, and double-check at submit time so it can't
    // slip through unnoticed even if the hint went unread.
    document.querySelectorAll(".recert-row").forEach((row) => {
      const select = row.querySelector(".recert-select");
      const textarea = row.querySelector(".recert-comment");
      const hint = row.querySelector(".recert-hint");
      const badge = row.querySelector(".changed-badge");
      const originalComment = textarea.value;

      function refresh() {
        const commentChanged = textarea.value !== originalComment;
        const orphaned = commentChanged && select.value === "";
        const changed = select.value !== "" || commentChanged;
        if (hint) hint.hidden = !orphaned;
        if (badge) badge.hidden = !changed;
        row.classList.toggle("comment-orphan", orphaned);
        row.classList.toggle("changed", changed);
      }

      select.addEventListener("change", () => {
        refresh();
        updateRecertState();
      });
      textarea.addEventListener("input", refresh);
    });

    const recertFormEl = document.getElementById("recert-form");
    if (recertFormEl) {
      recertFormEl.addEventListener("submit", (e) => {
        const orphanCount = document.querySelectorAll(".recert-row.comment-orphan").length;
        if (orphanCount === 0) return;
        const proceed = window.confirm(
          `${orphanCount} Kommentar(e) haben keine Auswahl bei "Noch benötigt?" und werden ` +
            `deshalb NICHT gespeichert. Trotzdem fortfahren?`
        );
        if (!proceed) e.preventDefault();
      });
    }
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
  if (recertForm) {
    // Runs after wireRecertification()'s own submit listener (registration
    // order), so e.defaultPrevented is already set if the user cancelled the
    // orphaned-comment confirm dialog - in that case nothing was actually
    // submitted, so the unsaved-changes warning must stay armed.
    recertForm.addEventListener("submit", (e) => {
      if (!e.defaultPrevented) submittingFormId = "recert-form";
    });
  }

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
