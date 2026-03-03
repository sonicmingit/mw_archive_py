(function() {
  const modal = document.getElementById('manualImportModal');
  if (!modal) return;

  const openers = document.querySelectorAll('[data-manual-import-open]');
  const closers = modal.querySelectorAll('[data-manual-import-close]');
  const form = document.getElementById('manualImportForm');
  const msgEl = document.getElementById('manualImportMsg');
  const submitBtn = document.getElementById('manualImportSubmit');

  const instanceAddBtn = document.getElementById('manualAddInstance');
  const instancePicker = document.getElementById('manualInstancePicker');
  const instanceList = document.getElementById('instanceDescList');
  const instanceEntries = [];

  const draftSessionInput = document.getElementById('manualDraftSessionId');
  const draftOverridesInput = document.getElementById('manualDraftOverrides');
  const parse3mfBtn = document.getElementById('manualParse3mf');
  const parse3mfInput = document.getElementById('manual3mfPicker');
  const draftPreview = document.getElementById('manualParsedPreview');
  const draftCover = document.getElementById('manualDraftCover');
  const draftTitle = document.getElementById('manualDraftTitle');
  const draftDesigner = document.getElementById('manualDraftDesigner');
  const draftDesignList = document.getElementById('manualDraftDesignList');
  const draftAttachmentList = document.getElementById('manualDraftAttachmentList');
  const parsedInstanceList = document.getElementById('parsedInstanceList');
  const summaryEditor = document.getElementById('manualSummaryEditor');
  const summaryTextInput = document.getElementById('manualSummaryText');
  const summaryHtmlInput = document.getElementById('manualSummaryHtml');
  const richButtons = modal.querySelectorAll('[data-rich-cmd]');
  const parseInstancesBtn = document.getElementById('manualParseInstances');

  let parsedDraft = null;

  function setMsg(text, isError, isSuccess) {
    if (!msgEl) return;
    msgEl.textContent = text || '';
    msgEl.classList.remove('error');
    msgEl.classList.remove('success');
    if (isError) msgEl.classList.add('error');
    if (isSuccess) msgEl.classList.add('success');
  }

  function refreshInstanceLabels() {
    instanceEntries.forEach((entry, idx) => {
      entry.nameEl.textContent = `实例 ${idx + 1}: ${entry.file.name}`;
    });
  }

  function normalizeDraftFileName(value) {
    return String(value || '').replace(/^s\d+_/i, '');
  }

  function fileStem(name) {
    const n = normalizeDraftFileName(name);
    const dot = n.lastIndexOf('.');
    return dot > 0 ? n.slice(0, dot) : n;
  }

  function clearInstanceEntries() {
    instanceEntries.splice(0, instanceEntries.length);
    if (instanceList) instanceList.innerHTML = '';
  }

  function clearDraftPreview() {
    parsedDraft = null;
    if (draftSessionInput) draftSessionInput.value = '';
    if (draftOverridesInput) draftOverridesInput.value = '[]';
    if (draftPreview) draftPreview.classList.add('hidden');
    if (parsedInstanceList) parsedInstanceList.innerHTML = '';
    if (draftDesignList) draftDesignList.innerHTML = '';
    if (draftAttachmentList) draftAttachmentList.innerHTML = '';
    if (draftCover) draftCover.src = '';
    if (draftTitle) draftTitle.textContent = '';
    if (draftDesigner) draftDesigner.textContent = '';
  }

  function htmlToPlainText(html) {
    const div = document.createElement('div');
    div.innerHTML = html || '';
    return (div.textContent || div.innerText || '').trim();
  }

  function normalizeSummaryHtml(html) {
    const v = String(html || '').replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, '').trim();
    if (!v || v === '<br>' || v === '<p><br></p>') return '';
    return v;
  }

  function setSummaryEditor(contentHtml, fallbackText) {
    if (!summaryEditor) return;
    const html = normalizeSummaryHtml(contentHtml);
    if (html) {
      summaryEditor.innerHTML = html;
    } else {
      const text = String(fallbackText || '').trim();
      summaryEditor.innerText = text;
    }
    syncSummaryFields();
  }

  function syncSummaryFields() {
    if (!summaryEditor) return;
    const html = normalizeSummaryHtml(summaryEditor.innerHTML);
    const plain = htmlToPlainText(html || summaryEditor.innerText || '');
    if (summaryHtmlInput) summaryHtmlInput.value = html;
    if (summaryTextInput) summaryTextInput.value = plain;
  }

  function openModal() {
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    setMsg('');
  }

  openers.forEach((btn) => btn.addEventListener('click', openModal));
  closers.forEach((btn) => btn.addEventListener('click', closeModal));
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
  });

  if (summaryEditor) {
    summaryEditor.addEventListener('input', syncSummaryFields);
    summaryEditor.addEventListener('blur', syncSummaryFields);
  }

  richButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      if (!summaryEditor) return;
      summaryEditor.focus();
      const cmd = btn.getAttribute('data-rich-cmd') || '';
      const val = btn.getAttribute('data-rich-value') || null;
      try {
        document.execCommand(cmd, false, val);
      } catch (_) {}
      syncSummaryFields();
    });
  });

  function addInstanceFiles(files) {
    if (!instanceList || !files || !files.length) return;
    Array.from(files).forEach((file, idx) => {
      const row = document.createElement('div');
      row.className = 'file-desc-item';

      const name = document.createElement('div');
      name.className = 'file-name';
      name.textContent = `实例 ${instanceEntries.length + idx + 1}: ${file.name}`;

      const titleLabel = document.createElement('label');
      titleLabel.textContent = '实例标题';
      const titleInput = document.createElement('input');
      titleInput.type = 'text';
      titleInput.value = fileStem(file.name);

      const label = document.createElement('label');
      label.textContent = '实例介绍';
      const input = document.createElement('textarea');
      input.setAttribute('data-instance-desc', '1');
      input.rows = 2;

      const picLabel = document.createElement('label');
      picLabel.textContent = '实例图片 (多选)';
      const picInput = document.createElement('input');
      picInput.type = 'file';
      picInput.accept = 'image/*';
      picInput.multiple = true;
      picInput.setAttribute('data-instance-pics', '1');

      const parseHint = document.createElement('div');
      parseHint.className = 'manual-help';
      const parsedGallery = document.createElement('div');
      parsedGallery.className = 'manual-mini-gallery';

      const actions = document.createElement('div');
      actions.className = 'file-desc-actions';
      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'manual-btn danger';
      removeBtn.textContent = '移除';
      removeBtn.addEventListener('click', () => {
        const index = instanceEntries.findIndex((entry) => entry.row === row);
        if (index >= 0) instanceEntries.splice(index, 1);
        row.remove();
        refreshInstanceLabels();
      });
      actions.appendChild(removeBtn);

      row.appendChild(name);
      row.appendChild(titleLabel);
      row.appendChild(titleInput);
      row.appendChild(label);
      row.appendChild(input);
      row.appendChild(picLabel);
      row.appendChild(picInput);
      row.appendChild(parseHint);
      row.appendChild(parsedGallery);
      row.appendChild(actions);
      instanceList.appendChild(row);
      instanceEntries.push({
        file,
        nameEl: name,
        titleEl: titleInput,
        descEl: input,
        picEl: picInput,
        hintEl: parseHint,
        galleryEl: parsedGallery,
        row,
      });
    });
    refreshInstanceLabels();
  }

  function renderDraftInstances(instances) {
    if (!parsedInstanceList) return;
    parsedInstanceList.innerHTML = '';
    (instances || []).forEach((inst, idx) => {
      const card = document.createElement('div');
      card.className = 'manual-draft-inst';

      const head = document.createElement('div');
      head.className = 'manual-draft-inst-head';
      const left = document.createElement('div');
      left.className = 'left';

      const enable = document.createElement('input');
      enable.type = 'checkbox';
      enable.checked = true;
      enable.setAttribute('data-draft-enabled', String(idx));
      left.appendChild(enable);

      const fileTag = document.createElement('span');
      fileTag.className = 'manual-help';
      const preferredName = inst.sourceFileName || inst.name || '';
      fileTag.textContent = normalizeDraftFileName(preferredName);
      left.appendChild(fileTag);
      head.appendChild(left);
      card.appendChild(head);

      const titleLabel = document.createElement('label');
      titleLabel.textContent = `实例 ${idx + 1} 标题`;
      const titleInput = document.createElement('input');
      titleInput.type = 'text';
      titleInput.className = 'manual-draft-inst-title';
      titleInput.value = inst.title || '';
      titleInput.setAttribute('data-draft-title', String(idx));

      const summaryLabel = document.createElement('label');
      summaryLabel.textContent = '实例介绍';
      const summaryInput = document.createElement('textarea');
      summaryInput.rows = 2;
      summaryInput.value = inst.summary || '';
      summaryInput.setAttribute('data-draft-summary', String(idx));

      card.appendChild(titleLabel);
      card.appendChild(titleInput);
      card.appendChild(summaryLabel);
      card.appendChild(summaryInput);
      parsedInstanceList.appendChild(card);
    });
  }

  function renderDraftAssets(draft) {
    if (draftDesignList) {
      draftDesignList.innerHTML = '';
      const designUrls = Array.isArray(draft.designUrls) ? draft.designUrls : [];
      designUrls.forEach((url, idx) => {
        const img = document.createElement('img');
        img.className = 'manual-draft-thumb';
        img.src = String(url || '');
        img.alt = `design-${idx + 1}`;
        draftDesignList.appendChild(img);
      });
      if (!designUrls.length) {
        const empty = document.createElement('div');
        empty.className = 'manual-help';
        empty.textContent = '未识别到设计图片';
        draftDesignList.appendChild(empty);
      }
    }
    if (draftAttachmentList) {
      draftAttachmentList.innerHTML = '';
      const files = Array.isArray(draft.attachmentUrls) ? draft.attachmentUrls : [];
      files.forEach((item) => {
        const div = document.createElement('div');
        div.className = 'manual-draft-file';
        div.textContent = normalizeDraftFileName(item && item.name ? item.name : '');
        draftAttachmentList.appendChild(div);
      });
      if (!files.length) {
        const empty = document.createElement('div');
        empty.className = 'manual-help';
        empty.textContent = '未识别到附件';
        draftAttachmentList.appendChild(empty);
      }
    }
  }

  function mapParsedInstancesToEntries(instances) {
    const parsed = Array.isArray(instances) ? instances.slice() : [];
    const parsedByName = new Map();
    parsed.forEach((inst) => {
      const key = normalizeDraftFileName(inst && (inst.sourceFileName || inst.name || '')).toLowerCase();
      if (!key) return;
      if (!parsedByName.has(key)) parsedByName.set(key, []);
      parsedByName.get(key).push(inst);
    });

    const picks = [];
    instanceEntries.forEach((entry) => {
      const key = normalizeDraftFileName(entry.file && entry.file.name).toLowerCase();
      const queue = parsedByName.get(key) || [];
      if (queue.length) {
        picks.push(queue.shift());
        return;
      }
      picks.push(parsed.shift() || null);
    });
    return picks;
  }

  function applyInstanceParsedResult(entry, parsed, idx) {
    if (!entry || !parsed) return;
    const parsedTitle = String(parsed.title || '').trim();
    const parsedSummary = String(parsed.summary || '').trim();
    const currentTitle = entry.titleEl ? String(entry.titleEl.value || '').trim() : '';
    const currentSummary = entry.descEl ? String(entry.descEl.value || '').trim() : '';
    if (entry.titleEl && (!currentTitle || currentTitle === fileStem(entry.file.name))) {
      entry.titleEl.value = parsedTitle || fileStem(entry.file.name);
    }
    if (entry.descEl && !currentSummary && parsedSummary) {
      entry.descEl.value = parsedSummary;
    }

    if (entry.hintEl) {
      const picCount = Array.isArray(parsed.pictures) ? parsed.pictures.length : 0;
      const plateCount = Array.isArray(parsed.plates) ? parsed.plates.length : 0;
      entry.hintEl.textContent = `已识别：实例 ${idx + 1}，图片 ${picCount} 张，盘 ${plateCount} 个`;
    }
    if (entry.galleryEl) {
      entry.galleryEl.innerHTML = '';
      const pics = Array.isArray(parsed.pictures) ? parsed.pictures : [];
      pics.slice(0, 8).forEach((pic, pidx) => {
        const preview = pic && pic.previewUrl ? String(pic.previewUrl) : '';
        if (!preview) return;
        const img = document.createElement('img');
        img.src = preview;
        img.alt = `inst-${idx + 1}-pic-${pidx + 1}`;
        entry.galleryEl.appendChild(img);
      });
    }
  }

  function collectDraftOverrides() {
    if (!parsedDraft || !parsedDraft.instances) return [];
    return parsedDraft.instances.map((_, idx) => {
      const enabledEl = parsedInstanceList.querySelector(`[data-draft-enabled="${idx}"]`);
      const titleEl = parsedInstanceList.querySelector(`[data-draft-title="${idx}"]`);
      const summaryEl = parsedInstanceList.querySelector(`[data-draft-summary="${idx}"]`);
      return {
        enabled: !!(enabledEl && enabledEl.checked),
        title: titleEl ? titleEl.value : '',
        summary: summaryEl ? summaryEl.value : '',
      };
    });
  }

  async function parse3mfFiles() {
    if (!parse3mfInput || !parse3mfInput.files || !parse3mfInput.files.length) {
      setMsg('请先选择 3MF 文件', true);
      return;
    }
    const fd = new FormData();
    Array.from(parse3mfInput.files).forEach((f) => fd.append('files', f));

    const oldText = parse3mfBtn ? parse3mfBtn.textContent : '';
    if (parse3mfBtn) {
      parse3mfBtn.disabled = true;
      parse3mfBtn.textContent = '识别中...';
    }
    setMsg('正在解析 3MF ...');
    try {
      const res = await fetch('/api/manual/3mf/parse', { method: 'POST', body: fd });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || '解析失败');
      }
      const data = await res.json();
      const draft = data && data.draft ? data.draft : null;
      if (!draft) throw new Error('解析结果为空');
      parsedDraft = draft;

      if (draftSessionInput) draftSessionInput.value = draft.sessionId || '';
      if (draftTitle) draftTitle.textContent = draft.title || '未命名模型';
      if (draftDesigner) draftDesigner.textContent = draft.designer ? `作者: ${draft.designer}` : '作者: 未识别';
      if (draftCover) {
        draftCover.src = draft.coverUrl || '';
        draftCover.style.display = draft.coverUrl ? '' : 'none';
      }
      if (draftPreview) draftPreview.classList.remove('hidden');

      renderDraftAssets(draft);
      renderDraftInstances(draft.instances || []);

      const titleInput = form.querySelector('[name="title"]');
      if (titleInput && !titleInput.value.trim()) titleInput.value = draft.title || '';
      const currentSummaryText = summaryTextInput ? summaryTextInput.value.trim() : '';
      const currentSummaryHtml = summaryHtmlInput ? summaryHtmlInput.value.trim() : '';
      if (!currentSummaryText && !currentSummaryHtml) {
        setSummaryEditor(draft.summaryHtml || '', draft.summary || '');
      }
      const sourceInput = form.querySelector('[name="sourceLink"]');
      if (sourceInput && !sourceInput.value.trim()) sourceInput.value = '';

      setMsg('3MF 识别完成，可补充信息后保存归档', false, true);
    } catch (err) {
      setMsg(`3MF 识别失败：${err.message || err}`, true);
    } finally {
      if (parse3mfBtn) {
        parse3mfBtn.disabled = false;
        parse3mfBtn.textContent = oldText || '识别并填充';
      }
    }
  }

  async function parseAddedInstanceFiles() {
    if (!instanceEntries.length) {
      setMsg('请先添加实例文件', true);
      return;
    }
    const fd = new FormData();
    instanceEntries.forEach((entry) => {
      if (entry && entry.file) fd.append('files', entry.file);
    });
    const oldText = parseInstancesBtn ? parseInstancesBtn.textContent : '';
    if (parseInstancesBtn) {
      parseInstancesBtn.disabled = true;
      parseInstancesBtn.textContent = '识别中...';
    }
    setMsg('正在识别实例配置...');
    try {
      const res = await fetch('/api/manual/3mf/parse', { method: 'POST', body: fd });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || '实例识别失败');
      }
      const data = await res.json();
      const draft = data && data.draft ? data.draft : null;
      if (!draft || !Array.isArray(draft.instances)) throw new Error('实例识别结果为空');
      const mapped = mapParsedInstancesToEntries(draft.instances);
      mapped.forEach((inst, idx) => applyInstanceParsedResult(instanceEntries[idx], inst, idx));
      setMsg('实例识别完成：已填充实例标题/介绍，并回显配置图片', false, true);
    } catch (err) {
      setMsg(`实例识别失败：${err.message || err}`, true);
    } finally {
      if (parseInstancesBtn) {
        parseInstancesBtn.disabled = false;
        parseInstancesBtn.textContent = oldText || '识别实例信息';
      }
    }
  }

  if (instanceAddBtn && instancePicker) {
    instanceAddBtn.addEventListener('click', () => instancePicker.click());
    instancePicker.addEventListener('change', () => {
      addInstanceFiles(instancePicker.files);
      instancePicker.value = '';
    });
  }

  if (parse3mfBtn) parse3mfBtn.addEventListener('click', parse3mfFiles);
  if (parseInstancesBtn) parseInstancesBtn.addEventListener('click', parseAddedInstanceFiles);
  syncSummaryFields();

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!form.checkValidity()) {
        form.reportValidity();
        return;
      }

      if (draftOverridesInput) {
        draftOverridesInput.value = JSON.stringify(collectDraftOverrides());
      }
      syncSummaryFields();

      const formData = new FormData();
      const titleInput = form.querySelector('[name="title"]');
      const modelLinkInput = form.querySelector('[name="modelLink"]');
      const sourceLinkInput = form.querySelector('[name="sourceLink"]');
      const summaryInput = form.querySelector('[name="summary"]');
      const summaryHtmlFormInput = form.querySelector('[name="summary_html"]');
      const tagsInput = form.querySelector('[name="tags"]');

      formData.append('title', titleInput ? titleInput.value : '');
      formData.append('modelLink', modelLinkInput ? modelLinkInput.value : '');
      formData.append('sourceLink', sourceLinkInput ? sourceLinkInput.value : '');
      formData.append('summary', summaryInput ? summaryInput.value : '');
      formData.append('summary_html', summaryHtmlFormInput ? summaryHtmlFormInput.value : '');
      formData.append('tags', tagsInput ? tagsInput.value : '');
      formData.append('draft_session_id', draftSessionInput ? draftSessionInput.value : '');
      formData.append('draft_instance_overrides', draftOverridesInput ? draftOverridesInput.value : '[]');

      const coverInput = form.querySelector('[name="cover"]');
      if (coverInput && coverInput.files && coverInput.files[0]) {
        formData.append('cover', coverInput.files[0]);
      }
      const designInput = form.querySelector('[name="design_images"]');
      if (designInput && designInput.files) {
        Array.from(designInput.files).forEach((f) => formData.append('design_images', f));
      }

      instanceEntries.forEach((entry) => formData.append('instance_files', entry.file));

      const attachmentsInput = form.querySelector('[name="attachments"]');
      if (attachmentsInput && attachmentsInput.files) {
        Array.from(attachmentsInput.files).forEach((f) => formData.append('attachments', f));
      }

      const descs = instanceEntries.map((entry) => entry.descEl.value || '');
      const titles = instanceEntries.map((entry) => entry.titleEl ? (entry.titleEl.value || '') : '');
      const picInputs = instanceEntries.map((entry) => entry.picEl);
      const picCounts = [];
      const picFiles = [];
      picInputs.forEach((input) => {
        const files = input.files ? Array.from(input.files) : [];
        picCounts.push(files.length);
        files.forEach((f) => picFiles.push(f));
      });
      formData.append('instance_descs', JSON.stringify(descs));
      formData.append('instance_titles', JSON.stringify(titles));
      formData.append('instance_picture_counts', JSON.stringify(picCounts));
      picFiles.forEach((f) => formData.append('instance_pictures', f));

      if (submitBtn) submitBtn.disabled = true;
      setMsg('上传中...');
      try {
        const res = await fetch('/api/models/manual', { method: 'POST', body: formData });
        if (!res.ok) {
          const err = await res.text();
          throw new Error(err || '导入失败');
        }
        const data = await res.json();
        form.reset();
        if (summaryEditor) summaryEditor.innerHTML = '';
        syncSummaryFields();
        clearInstanceEntries();
        clearDraftPreview();
        setMsg('导入成功', false, true);
        closeModal();
        alert(`导入完成：${data.work_dir || data.base_name || ''}`);
        window.location.reload();
      } catch (err) {
        setMsg(`导入失败：${err.message || err}`, true);
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });
  }
})();

