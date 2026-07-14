(function() {
  'use strict';

  let festivals = [];
  let activeFilters = {
    status: 'all',
    city: 'all',
    genre: 'all',
    search: ''
  };

  const STATUS_MAP = {
    accepting: { label: 'Приём заявок', class: 'accepting' },
    upcoming: { label: 'Скоро', class: 'upcoming' },
    past: { label: 'Прошёл', class: 'past' },
    active: { label: 'Активен', class: 'accepting' },
    paused: { label: 'Приостановлен', class: 'paused' },
    cancelled: { label: 'Закрыт', class: 'cancelled' },
    unknown: { label: 'Требует верификации', class: 'unknown' }
  };

  async function loadFestivals() {
    try {
      const response = await fetch('festivals.json');
      const data = await response.json();
      festivals = data.festivals;
      document.getElementById('lastUpdated').textContent = data.lastUpdated;
      populateCityFilter();
      render();
    } catch (err) {
      console.error('Ошибка загрузки данных:', err);
    }
  }

  function populateCityFilter() {
    const cities = [...new Set(festivals.map(f => f.city))].sort();
    const select = document.querySelector('[data-filter="city"]');
    cities.forEach(city => {
      const opt = document.createElement('option');
      opt.value = city;
      opt.textContent = city;
      select.appendChild(opt);
    });
  }

  function filterFestivals() {
    return festivals.filter(f => {
      if (activeFilters.status !== 'all') {
        if (activeFilters.status === 'active' && f.status !== 'active' && f.status !== 'accepting') return false;
        if (activeFilters.status !== 'active' && f.status !== activeFilters.status) return false;
      }
      if (activeFilters.city !== 'all' && f.city !== activeFilters.city) return false;
      if (activeFilters.genre !== 'all' && !f.genres.includes(activeFilters.genre)) return false;
      if (activeFilters.search) {
        const q = activeFilters.search.toLowerCase();
        const searchable = (f.name + ' ' + f.fullName + ' ' + f.city + ' ' + f.description).toLowerCase();
        if (!searchable.includes(q)) return false;
      }
      return true;
    });
  }

  function getCountdown(deadlineStr) {
    if (!deadlineStr) return null;
    const deadline = new Date(deadlineStr);
    const now = new Date();
    const diff = deadline - now;

    if (diff < 0) return { text: 'Дедлайн прошёл', passed: true };

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const months = Math.floor(days / 30);

    if (months > 0) {
      const remDays = days % 30;
      return {
        text: `${months} мес ${remDays} дн`,
        passed: false
      };
    }
    return {
      text: `${days} дн`,
      passed: false
    };
  }

  function renderCard(festival) {
    const status = STATUS_MAP[festival.status] || STATUS_MAP.unknown;
    const countdown = getCountdown(festival.submissionDeadline);
    const isUnknown = festival.status === 'unknown';

    let deadlineBlock = '';
    if (festival.submissionDeadline) {
      const passedClass = countdown.passed ? 'card__deadline--passed' : '';
      deadlineBlock = `
        <div class="card__deadline ${passedClass}">
          <span class="card__deadline-label">Дедлайн подачи</span>
          <span class="card__countdown">${countdown.text}</span>
        </div>`;
    }

    let noteBlock = '';
    if (festival.notes) {
      noteBlock = `<div class="card__note">${festival.notes}</div>`;
    }

    const websiteLink = festival.website
      ? `<a href="${festival.website}" class="card__link card__link--secondary" target="_blank" rel="noopener">Сайт фестиваля ↗</a>`
      : `<span class="card__link card__link--secondary card__link--disabled">Сайт недоступен</span>`;

    const submitLink = festival.submissionUrl
      ? `<a href="${festival.submissionUrl}" class="card__link card__link--primary" target="_blank" rel="noopener">Подать заявку ↗</a>`
      : '';

    const tags = festival.genres.map(g =>
      `<span class="card__tag">${g}</span>`
    ).join('');

    const formats = festival.formats.map(f =>
      `<span class="card__tag">${f}</span>`
    ).join('');

    return `
      <article class="card ${isUnknown ? 'card--unknown' : ''} ${festival.status === 'cancelled' ? 'card--cancelled' : ''} ${festival.status === 'paused' ? 'card--paused' : ''}" data-id="${festival.id}">
        <div class="card__header">
          <h3 class="card__name">${festival.name}</h3>
          <span class="card__status card__status--${status.class}">${status.label}</span>
        </div>
        <div class="card__fullName">${festival.fullName}</div>
        <div class="card__meta">
          <span class="card__meta-item">
            <span class="card__meta-icon">📍</span>
            ${festival.city}
          </span>
          <span class="card__meta-item">
            <span class="card__meta-icon">🎯</span>
            ${festival.focus}
          </span>
          ${festival.festivalDates ? `
          <span class="card__meta-item">
            <span class="card__meta-icon">📅</span>
            ${festival.festivalDates}
          </span>` : ''}
        </div>
        <p class="card__description">${festival.description}</p>
        <div class="card__tags">
          ${tags}
          ${formats}
        </div>
        ${deadlineBlock}
        ${noteBlock}
        <div class="card__footer">
          ${websiteLink}
          ${submitLink}
        </div>
      </article>`;
  }

  function renderModal(festival) {
    const status = STATUS_MAP[festival.status] || STATUS_MAP.unknown;
    const countdown = getCountdown(festival.submissionDeadline);

    const websiteLink = festival.website
      ? `<a href="${festival.website}" class="btn btn--primary" target="_blank" rel="noopener">Сайт фестиваля ↗</a>`
      : '';

    const submitLink = festival.submissionUrl
      ? `<a href="${festival.submissionUrl}" class="btn btn--primary" target="_blank" rel="noopener">Подать заявку ↗</a>`
      : '';

    let deadlineBlock = '';
    if (festival.submissionDeadline) {
      const cls = countdown.passed ? 'modal__deadline--passed' : '';
      deadlineBlock = `
        <div class="modal__deadline ${cls}">
          <span class="modal__deadline-label">Дедлайн подачи заявок</span>
          <span class="modal__deadline-value">${countdown.text}</span>
        </div>`;
    }

    const tags = [...festival.genres, ...festival.formats].map(g =>
      `<span class="modal__tag">${g}</span>`
    ).join('');

    const noteBlock = festival.notes
      ? `<div class="modal__note">${festival.notes}</div>`
      : '';

    document.getElementById('modalContent').innerHTML = `
      <h2 class="modal__name">${festival.name}</h2>
      <div class="modal__fullName">${festival.fullName}</div>
      <span class="modal__status card__status--${status.class}">${status.label}</span>

      <div class="modal__grid">
        <div class="modal__field">
          <span class="modal__field-label">Город</span>
          <span class="modal__field-value">📍 ${festival.city}, ${festival.country}</span>
        </div>
        <div class="modal__field">
          <span class="modal__field-label">Фокус</span>
          <span class="modal__field-value">🎯 ${festival.focus}</span>
        </div>
        ${festival.festivalDates ? `
        <div class="modal__field">
          <span class="modal__field-label">Даты проведения</span>
          <span class="modal__field-value">📅 ${festival.festivalDates}</span>
        </div>` : ''}
        <div class="modal__field">
          <span class="modal__field-label">Форматы</span>
          <span class="modal__field-value">🎞 ${festival.formats.join(', ')}</span>
        </div>
      </div>

      <div class="modal__tags">${tags}</div>

      ${deadlineBlock}

      <div class="modal__section">
        <h4 class="modal__section-title">О фестивале</h4>
        <p>${festival.description}</p>
      </div>

      ${festival.requirements ? `
      <div class="modal__section">
        <h4 class="modal__section-title">Требования</h4>
        <p>${festival.requirements}</p>
      </div>` : ''}

      ${noteBlock}

      <div class="modal__links">
        ${websiteLink}
        ${submitLink}
      </div>
    `;
  }

  function openModal(festival) {
    renderModal(festival);
    const overlay = document.getElementById('modalOverlay');
    overlay.classList.add('modal-overlay--open');
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    const overlay = document.getElementById('modalOverlay');
    overlay.classList.remove('modal-overlay--open');
    document.body.style.overflow = '';
  }

  function render() {
    const filtered = filterFestivals();
    const grid = document.getElementById('festivalsGrid');
    const empty = document.getElementById('emptyState');
    const stats = document.getElementById('stats');

    if (filtered.length === 0) {
      grid.innerHTML = '';
      empty.style.display = 'block';
      stats.textContent = '';
      return;
    }

    empty.style.display = 'none';

    const accepting = filtered.filter(f => f.status === 'accepting' || f.status === 'active').length;
    const upcoming = filtered.filter(f => f.status === 'upcoming').length;
    const paused = filtered.filter(f => f.status === 'paused').length;
    const cancelled = filtered.filter(f => f.status === 'cancelled').length;
    const unknown = filtered.filter(f => f.status === 'unknown').length;

    const parts = [];
    parts.push(`${filtered.length} фестивалей`);
    if (accepting > 0) parts.push(`${accepting} активных`);
    if (upcoming > 0) parts.push(`${upcoming} скоро`);
    if (paused > 0) parts.push(`${paused} приостановленных`);
    if (cancelled > 0) parts.push(`${cancelled} закрытых`);
    if (unknown > 0) parts.push(`${unknown} требуют верификации`);
    stats.textContent = parts.join(' · ');

    grid.innerHTML = filtered.map(renderCard).join('');
  }

  function initFilters() {
    document.querySelectorAll('[data-filter="status"] .filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('[data-filter="status"] .filter-btn').forEach(b =>
          b.classList.remove('filter-btn--active'));
        btn.classList.add('filter-btn--active');
        activeFilters.status = btn.dataset.value;
        render();
      });
    });

    document.querySelectorAll('.filter-select').forEach(select => {
      select.addEventListener('change', () => {
        activeFilters[select.dataset.filter] = select.value;
        render();
      });
    });

    document.querySelector('[data-filter="search"]').addEventListener('input', (e) => {
      activeFilters.search = e.target.value;
      render();
    });

    document.getElementById('festivalsGrid').addEventListener('click', (e) => {
      const card = e.target.closest('.card');
      if (!card) return;
      if (e.target.closest('a')) return;
      const id = parseInt(card.dataset.id, 10);
      const festival = festivals.find(f => f.id === id);
      if (festival) openModal(festival);
    });

    document.getElementById('modalClose').addEventListener('click', closeModal);
    document.getElementById('modalOverlay').addEventListener('click', (e) => {
      if (e.target === e.currentTarget) closeModal();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeModal();
    });

    const subscribeForm = document.getElementById('subscribeForm');
    if (subscribeForm) {
      subscribeForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const email = document.getElementById('subscribeEmail').value;
        if (email) {
          const hint = document.querySelector('.about__cta-hint');
          if (hint) {
            hint.textContent = '✅ Спасибо! Мы отправим подтверждение на ' + email;
            hint.style.color = 'var(--accent)';
          }
          subscribeForm.style.display = 'none';
        }
      });
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    initFilters();
    loadFestivals();
  });
})();
