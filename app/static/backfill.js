// Back-dated revocation UI. Local-only: no external hosts are referenced.
(function () {
  const contextEl = document.getElementById('bf-context');
  if (!contextEl) return;
  const context = JSON.parse(contextEl.textContent);
  const notice = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };

  async function post(url, body) {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const answer = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(answer.message || '请求失败');
    return answer;
  }

  // M7 page: create a back-dated revocation.
  const submit = document.getElementById('bf-submit');
  if (submit) {
    submit.addEventListener('click', async () => {
      try {
        const answer = await post('/api/revocations', {
          run_id: context.root_id,
          standard_id: document.getElementById('bf-standard').value,
          effective_date: document.getElementById('bf-date').value,
          reason: document.getElementById('bf-reason').value,
        });
        location.href = '/revocations/' + answer.id;
      } catch (error) {
        notice('bf-notice', error.message);
      }
    });
  }

  // M7 page: resume an interrupted record.
  document.querySelectorAll('[data-resume]').forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        const answer = await post('/api/revocations/' + button.dataset.resume + '/resume', {});
        location.href = '/revocations/' + answer.id;
      } catch (error) {
        notice('bf-notice', error.message);
      }
    });
  });

  // Detail page: resume after an interrupted switch/derive.
  const resume = document.getElementById('resume');
  if (resume) {
    resume.addEventListener('click', async () => {
      try {
        const answer = await post('/api/revocations/' + context.revocation_id + '/resume', {});
        location.reload();
      } catch (error) {
        notice('resume-notice', error.message);
      }
    });
  }

  // Detail page: register retest destination (去向).
  document.querySelectorAll('[data-retest]').forEach((button) => {
    button.addEventListener('click', async () => {
      const id = button.dataset.retest;
      try {
        const answer = await post('/api/retests/' + id + '/disposition', {
          destination: document.getElementById('sel-' + id).value,
          note: document.getElementById('note-' + id).textContent,
        });
        document.getElementById('dest-' + id).textContent = answer.destination;
      } catch (error) {
        alert(error.message);
      }
    });
  });

  const print = document.getElementById('print');
  if (print) print.addEventListener('click', () => window.print());
})();
