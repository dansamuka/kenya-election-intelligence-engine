(() => {
  'use strict';

  const milestones = [
    ['2026-10-15', '15 Oct 2026', 'Political parties submit names and specimen signatures of authorised officials to IEBC'],
    ['2026-10-30', '30 Oct 2026', 'Party nomination rules certified by the Registrar of Political Parties'],
    ['2026-11-06', '6 Nov 2026', 'Certified nomination rules submitted to IEBC'],
    ['2026-12-09', '9 Dec 2026', 'Cut-off for aspirants taking part in harambees or public fundraising'],
    ['2027-02-10', '10 Feb 2027', 'Public officers intending to contest must resign'],
    ['2027-03-16', '16 Mar 2027', 'Parties submit membership, coalition, primary participant and venue details'],
    ['2027-03-17', '17–23 Mar 2027', 'IEBC gazettes people participating in party nominations'],
    ['2027-03-31', 'Mar–Apr 2027', 'Party primaries conducted', true],
    ['2027-05-08', '8/9 May 2027', 'Primaries and internal disputes essentially completed; independent-candidate party-exit deadline', true],
    ['2027-05-24', '24 May 2027', 'Presidential aspirants submit supporters from a majority of counties'],
    ['2027-05-29', '29 May–11 Jun 2027', 'IEBC formal candidate nomination and registration period'],
    ['2027-06-12', '12 Jun 2027', 'Latest date for lodging IEBC nomination disputes'],
    ['2027-06-23', '23 Jun 2027', 'Nomination disputes determined'],
    ['2027-06-25', '25 Jun 2027', 'Political parties submit lists for nominated seats'],
    ['2027-07-27', 'Around 27 Jul 2027', 'Parties and candidates submit chief election agents', true],
    ['2027-08-07', '7 Aug 2027', 'Campaigns end'],
    ['2027-08-10', '10 Aug 2027', '🇰🇪 GENERAL ELECTION']
  ].map(function (item) {
    return { date: new Date(item[0] + 'T00:00:00+03:00'), iso: item[0], label: item[1], title: item[2], approximate: !!item[3] };
  });

  const styles = document.createElement('style');
  styles.textContent = [
    '.election-calendar{background:linear-gradient(145deg,#0e2e22 0%,#153d2f 50%,#0b261d 100%);color:#edf3ef;overflow:hidden;position:relative}',
    '.election-calendar:before{content:"";position:absolute;width:420px;height:420px;border-radius:50%;right:-170px;top:-170px;background:radial-gradient(circle,rgba(95,211,163,.16),transparent 68%);pointer-events:none}',
    '.ec-head{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;position:relative}',
    '.ec-head .eyebrow{color:#8fc7ae}.ec-head .h-sec{color:#fff}.ec-head .sub{color:#b9cfc4}',
    '.ec-grid{display:grid;grid-template-columns:minmax(0,.86fr) minmax(360px,1.14fr);gap:24px;margin-top:30px;align-items:start;position:relative}',
    '.ec-panel{background:rgba(255,255,255,.075);border:1px solid rgba(255,255,255,.14);border-radius:22px;box-shadow:0 22px 60px rgba(0,0,0,.18);backdrop-filter:blur(10px)}',
    '.ec-count{padding:26px;position:sticky;top:76px}',
    '.ec-kicker{font-family:"Libre Franklin",sans-serif;font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:#8fc7ae;font-weight:800}',
    '.ec-next{font-family:"Libre Franklin",sans-serif;font-size:clamp(20px,2.5vw,28px);font-weight:900;line-height:1.15;margin:10px 0 4px;color:#fff}',
    '.ec-next-date{color:#b9cfc4;font-size:14px}',
    '.ec-digits{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:24px 0}',
    '.ec-digit{background:rgba(0,0,0,.18);border:1px solid rgba(255,255,255,.1);border-radius:14px;padding:14px 5px;text-align:center}',
    '.ec-num{display:block;font-family:"Libre Franklin",sans-serif;font-size:clamp(25px,4vw,42px);font-weight:900;line-height:1;color:#5fd3a3;font-variant-numeric:tabular-nums}',
    '.ec-unit{display:block;margin-top:7px;font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:#9dbbad;font-weight:700}',
    '.ec-progress-head{display:flex;justify-content:space-between;gap:12px;font-size:12px;color:#b9cfc4;margin-top:20px}',
    '.ec-progress{height:9px;background:rgba(255,255,255,.1);border-radius:99px;overflow:hidden;margin-top:8px}',
    '.ec-progress span{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#3fb985,#5fd3a3);transition:width .8s ease}',
    '.ec-election{display:flex;align-items:center;gap:13px;margin-top:22px;padding:15px;border-radius:15px;background:rgba(95,211,163,.1);border:1px solid rgba(95,211,163,.22)}',
    '.ec-flag{font-size:28px}.ec-election b{display:block;font-family:"Libre Franklin",sans-serif;font-size:15px;color:#fff}.ec-election small{color:#9dbbad}',
    '.ec-timeline{padding:8px 24px 8px 30px;max-height:690px;overflow:auto;scrollbar-color:#3f765f transparent}',
    '.ec-item{position:relative;padding:17px 4px 17px 25px;border-left:1px solid rgba(143,199,174,.3)}',
    '.ec-item:before{content:"";position:absolute;width:11px;height:11px;border-radius:50%;left:-6px;top:22px;background:#6e9585;border:3px solid #173d30;box-sizing:content-box}',
    '.ec-item.past{opacity:.54}.ec-item.past:before{background:#48695b}',
    '.ec-item.next{margin-left:-1px;border-left:3px solid #5fd3a3;background:linear-gradient(90deg,rgba(95,211,163,.12),transparent);border-radius:0 14px 14px 0}',
    '.ec-item.next:before{left:-8px;background:#5fd3a3;box-shadow:0 0 0 6px rgba(95,211,163,.12)}',
    '.ec-item.election:before{background:#fff}.ec-date{font-family:"Libre Franklin",sans-serif;font-size:12px;font-weight:800;color:#8fc7ae;letter-spacing:.02em}',
    '.ec-item.next .ec-date{color:#5fd3a3}.ec-title{font-size:13.5px;line-height:1.45;color:#e0ebe5;margin-top:4px}',
    '.ec-badge{display:inline-block;margin-left:7px;padding:2px 6px;border-radius:99px;background:rgba(184,114,42,.2);color:#e7b77f;font-size:9px;text-transform:uppercase;letter-spacing:.06em;vertical-align:1px}',
    '.ec-disclaimer{color:#8fa99c;font-size:11px;line-height:1.5;margin:18px 0 0}',
    '@media(max-width:800px){.ec-grid{grid-template-columns:1fr}.ec-count{position:relative;top:auto}.ec-timeline{max-height:none}.ec-head{display:block}}',
    '@media(max-width:420px){.ec-digits{gap:5px}.ec-digit{padding:12px 3px}.ec-count{padding:20px}.ec-timeline{padding-right:16px}}'
  ].join('');

  function build() {
    if (document.getElementById('key-dates')) return;

    document.head.appendChild(styles);
    const nav = document.querySelector('.nav');
    if (nav) {
      const link = document.createElement('a');
      link.href = '#key-dates';
      link.textContent = 'Key dates';
      nav.insertBefore(link, nav.firstChild);
    }

    const section = document.createElement('section');
    section.className = 'section election-calendar';
    section.id = 'key-dates';
    section.innerHTML =
      '<div class="wrap">' +
        '<div class="ec-head"><div><p class="eyebrow">Election calendar</p><h2 class="h-sec">The road to 10 August 2027</h2>' +
        '<p class="sub">Every major nomination, eligibility and campaign milestone in one live view.</p></div></div>' +
        '<div class="ec-grid">' +
          '<aside class="ec-panel ec-count" aria-live="polite">' +
            '<div class="ec-kicker">Next key date</div><div class="ec-next" id="ecNext">Loading…</div><div class="ec-next-date" id="ecNextDate"></div>' +
            '<div class="ec-digits">' +
              '<div class="ec-digit"><span class="ec-num" id="ecDays">000</span><span class="ec-unit">Days</span></div>' +
              '<div class="ec-digit"><span class="ec-num" id="ecHours">00</span><span class="ec-unit">Hours</span></div>' +
              '<div class="ec-digit"><span class="ec-num" id="ecMinutes">00</span><span class="ec-unit">Minutes</span></div>' +
              '<div class="ec-digit"><span class="ec-num" id="ecSeconds">00</span><span class="ec-unit">Seconds</span></div>' +
            '</div>' +
            '<div class="ec-progress-head"><span>2022 election</span><b id="ecProgressText">—</b><span>2027 election</span></div>' +
            '<div class="ec-progress"><span id="ecProgressBar"></span></div>' +
            '<div class="ec-election"><span class="ec-flag">🇰🇪</span><div><b>General Election</b><small>Tuesday, 10 August 2027</small></div></div>' +
            '<p class="ec-disclaimer">Dates marked approximate cover a range or a deadline reported as “around” that date. Always confirm filing requirements with IEBC and the Registrar of Political Parties.</p>' +
          '</aside>' +
          '<div class="ec-panel ec-timeline" id="ecTimeline" aria-label="2027 election milestones"></div>' +
        '</div>' +
      '</div>';

    const main = document.querySelector('main');
    const countdown = document.getElementById('countdown');
    if (countdown && countdown.nextSibling) main.insertBefore(section, countdown.nextSibling);
    else if (countdown) main.appendChild(section);
    else main.insertBefore(section, main.firstChild);

    const timeline = document.getElementById('ecTimeline');
    milestones.forEach(function (m, i) {
      const item = document.createElement('article');
      item.className = 'ec-item' + (i === milestones.length - 1 ? ' election' : '');
      item.dataset.iso = m.iso;
      item.innerHTML = '<div class="ec-date">' + m.label + (m.approximate ? '<span class="ec-badge">Approx.</span>' : '') +
        '</div><div class="ec-title">' + m.title + '</div>';
      timeline.appendChild(item);
    });

    update();
    window.setInterval(update, 1000);
  }

  function update() {
    const now = new Date();
    let next = milestones.find(function (m) { return m.date.getTime() > now.getTime(); });
    if (!next) next = milestones[milestones.length - 1];

    const remaining = Math.max(0, next.date.getTime() - now.getTime());
    const days = Math.floor(remaining / 86400000);
    const hours = Math.floor((remaining % 86400000) / 3600000);
    const minutes = Math.floor((remaining % 3600000) / 60000);
    const seconds = Math.floor((remaining % 60000) / 1000);
    const pad = function (n, size) { return String(n).padStart(size, '0'); };

    document.getElementById('ecNext').textContent = remaining ? next.title : 'Election day has arrived';
    document.getElementById('ecNextDate').textContent = next.label;
    document.getElementById('ecDays').textContent = pad(days, 3);
    document.getElementById('ecHours').textContent = pad(hours, 2);
    document.getElementById('ecMinutes').textContent = pad(minutes, 2);
    document.getElementById('ecSeconds').textContent = pad(seconds, 2);

    const cycleStart = new Date('2022-08-09T00:00:00+03:00');
    const election = milestones[milestones.length - 1].date;
    const progress = Math.max(0, Math.min(100, ((now - cycleStart) / (election - cycleStart)) * 100));
    document.getElementById('ecProgressBar').style.width = progress.toFixed(1) + '%';
    document.getElementById('ecProgressText').textContent = progress.toFixed(0) + '% through cycle';

    document.querySelectorAll('.ec-item').forEach(function (item) {
      const t = new Date(item.dataset.iso + 'T00:00:00+03:00');
      item.classList.toggle('past', t < now && item.dataset.iso !== next.iso);
      item.classList.toggle('next', item.dataset.iso === next.iso);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build);
  else build();
})();