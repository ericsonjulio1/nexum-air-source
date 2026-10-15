/* Shared presentation for Frappe Charts, ECharts and the Financial Overview.
 * Adapters leave data, chart types, scales, click handlers and formatters intact. */
(function () {
    const font = '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    const light = ['#168c83', '#557e94', '#876ab7', '#ba872a', '#356476', '#b96552', '#648d46', '#b16c95'];
    const dark = ['#53c6b7', '#91bad0', '#b09cda', '#e1b35c', '#78a9bc', '#e79b86', '#a0c180', '#d598bb'];
    const isDark = () => document.documentElement.getAttribute('data-theme') === 'dark';
    const palette = () => (isDark() ? dark : light).slice();
    const mapOneOrMany = (value, fn) => Array.isArray(value) ? value.map(fn) : value ? fn(value) : value;
    const charts = new Set(), registered = new WeakSet();
    function frappeOptions(options) {
        if (!options || options.type === 'heatmap') return options;
        return {...options, colors: palette(),
            lineOptions: {regionFill: 0, dotSize: 4, ...options.lineOptions},
        };
    }
    function echartsOptions(options, instance) {
        if (!options) return options;
        const colors = palette(), ink = isDark() ? '#e5e7eb' : '#202527';
        const muted = isDark() ? '#bbc5ca' : '#5b6468', border = isDark() ? '#38444b' : '#e6e9eb';
        const output = {...options, color: colors,
            textStyle: {...options.textStyle, fontFamily: font, color: ink},
            backgroundColor: 'transparent',
        };
        const axis = a => ({...a,
            axisLabel: {...a.axisLabel, color: muted, fontSize: 12, hideOverlap: true},
            axisLine: {...a.axisLine, lineStyle: {...a.axisLine?.lineStyle, color: border}},
            splitLine: {...a.splitLine, lineStyle: {...a.splitLine?.lineStyle, color: border}},
        });
        for (const key of ['xAxis', 'yAxis', 'radiusAxis', 'angleAxis']) {
            if (options[key]) output[key] = mapOneOrMany(options[key], axis);
        }
        if (options.title) output.title = mapOneOrMany(options.title, t => ({...t, textStyle: {...t.textStyle, color: ink, fontFamily: font, fontSize: 15, fontWeight: 600}}));
        if (options.legend) output.legend = mapOneOrMany(options.legend, l => ({...l, textStyle: {...l.textStyle, color: muted, fontFamily: font, fontSize: 12}}));
        if (options.tooltip) output.tooltip = {...options.tooltip, backgroundColor: isDark() ? '#20282e' : '#fff', borderColor: border, textStyle: {...options.tooltip.textStyle, color: ink, fontFamily: font, fontSize: 12}};
        // Explicit point colours and visual maps encode status, thresholds or a
        // user's saved choices. Preserve those; brand the default series only.
        if (options.series) output.series = mapOneOrMany(options.series, (series) => ({...series,
            labelLayout: {hideOverlap: true, ...series.labelLayout},
        }));
        const element = instance?.getDom?.();
        if (element) {
            element.classList.add('nx-report-chart');
            if (!registered.has(instance) && typeof WeakRef !== 'undefined') { charts.add(new WeakRef(instance)); registered.add(instance); }
        }
        return output;
    }
    window.NexumCharts = {palette, frappeOptions, echartsOptions};
    if (typeof MutationObserver !== 'undefined') new MutationObserver(() => {
        for (const reference of charts) {
            const chart = reference.deref();
            if (!chart || chart.isDisposed() || !chart.getDom()?.isConnected) { charts.delete(reference); continue; }
            chart.setOption(echartsOptions(chart.getOption(), chart));
        }
    }).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
})();
