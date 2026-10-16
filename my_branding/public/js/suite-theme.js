/* One signed-in preference: the same User.desk_theme used by Nexum Air Desk.
 * Seed before Vue starts; an intentional native SPA toggle also updates Desk.
 * No browser-local preference from another user can override this user's choice. */
(function () {
    const config = window.__NEXUM_BRAND__;
    if (!config || !config.theme) return;
    const root = document.documentElement;
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const normal = value => ({light: 'light', dark: 'dark', automatic: 'system', auto: 'system', system: 'system'})[String(value).toLowerCase()];
    let choice = normal(config.theme) || 'light';
    let confirmed = choice;
    let choiceVersion = 0;
    let saving = Promise.resolve();
    const read = key => { try { return localStorage.getItem(key); } catch { return null; } };
    const write = (key, value) => { try { localStorage.setItem(key, value); } catch {} };
    function paint() {
        const resolved = choice === 'system' ? (media.matches ? 'dark' : 'light') : choice;
        root.setAttribute('data-theme', resolved);
        root.classList.toggle('dark', resolved === 'dark');
        root.style.colorScheme = resolved;
    }
    function seed() {
        write('theme', choice);
        write('vueuse-color-scheme', choice === 'system' ? 'auto' : choice);
        paint();
    }
    seed();
    function save(next) {
        next = normal(next);
        if (!next || next === choice) return saving;
        const version = ++choiceVersion;
        choice = next;
        seed();
        if (!config.theme_csrf) return saving;
        saving = saving.catch(() => {}).then(async () => {
            // Desk unlock refreshes the SPA's shared token through idle_activity;
            // this boot-time config still belongs to the expired session.
            const csrf = [window.csrf_token, window.frappe?.csrf_token, config.theme_csrf]
                .find(token => token && !String(token).includes('{{') && token !== 'None');
            if (!csrf) throw new Error('A valid session token is required to save the theme');
            const response = await fetch('/api/method/frappe.core.doctype.user.user.switch_theme', {
                method: 'POST', credentials: 'same-origin',
                headers: {'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrf},
                body: JSON.stringify({theme: {light: 'Light', dark: 'Dark', system: 'Automatic'}[next]}),
            });
            if (!response.ok) throw new Error('Theme preference could not be saved');
            confirmed = next;
        }).catch(() => {
            if (version === choiceVersion) { choice = confirmed; seed(); }
            const notice = document.createElement('div');
            notice.setAttribute('role', 'alert');
            notice.className = 'nx-theme-error';
            notice.textContent = 'Your theme change could not be saved. Please try again.';
            document.body?.appendChild(notice);
            setTimeout(() => notice.remove(), 6000);
        });
        return saving;
    }
    window.NexumTheme = {setChoice: save, getChoice: () => choice};
    // Native toggles update storage and the root attribute in the same event.
    // Reading after that event avoids observing a half-applied toggle.
    new MutationObserver(() => {
        const key = location.pathname.startsWith('/builder') ? 'vueuse-color-scheme' : 'theme';
        const selected = normal(read(key));
        if (selected && selected !== choice) save(selected);
    }).observe(root, {attributes: true, attributeFilter: ['data-theme', 'class']});
    media.addEventListener('change', () => { if (choice === 'system') paint(); });
})();
