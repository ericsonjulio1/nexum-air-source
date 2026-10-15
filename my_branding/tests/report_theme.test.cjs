const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = {window: {}, document: {documentElement: {getAttribute: () => 'light'}}};
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname, '../public/js/report-theme.js'), 'utf8'), context);
const theme = context.window.NexumCharts;

test('report presentation keeps series, values, type, filters and tooltip callbacks intact', () => {
    const format = x => '$' + x;
    const options = {type: 'bar', data: {labels: ['A', 'B'], datasets: [{values: [-8, 13]}]},
        tooltipOptions: {formatTooltipY: format}, barOptions: {stacked: true}};
    const result = theme.frappeOptions(options);
    assert.equal(result.type, options.type);
    assert.equal(result.data, options.data);
    assert.equal(result.barOptions, options.barOptions);
    assert.equal(result.tooltipOptions.formatTooltipY, format);
    assert.equal(result.colors[0], '#168c83');
    assert.equal(options.colors, undefined, 'the caller keeps its reusable options');
    const heatmap = {type: 'heatmap', colors: ['#fff', '#168c83']};
    assert.equal(theme.frappeOptions(heatmap), heatmap);
});

test('ECharts styling preserves category meaning, stacks, maps and click data', () => {
    const formatter = point => point.name;
    const options = {series: [{type: 'bar', stack: 'cost', data: [{value: -6, itemStyle: {color: '#e74c3c'}}]},
        {type: 'map', map: 'world', data: [{name:'A', value:5}]}],
        visualMap: {min: 0, max: 100}, xAxis: {type:'category', data: ['A'], axisLabel: {formatter}},
        tooltip: {formatter}, legend: {data: ['Expense']}};
    const original = JSON.stringify(options);
    const result = theme.echartsOptions(options);
    assert.equal(result.series[0].data, options.series[0].data);
    assert.equal(result.series[0].stack, 'cost');
    assert.equal(result.series[1].map, 'world');
    assert.equal(result.visualMap, options.visualMap);
    assert.equal(result.xAxis.axisLabel.formatter, formatter);
    assert.equal(result.tooltip.formatter, formatter);
    assert.equal(result.xAxis.axisLabel.hideOverlap, true);
    assert.equal(JSON.stringify(options), original);
});
