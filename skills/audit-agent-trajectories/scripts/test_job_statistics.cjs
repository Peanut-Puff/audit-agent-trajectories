"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../assets/html/job-statistics.js"), "utf8");
const context = vm.createContext({});
vm.runInContext(source, context);
const calculate = message => JSON.parse(JSON.stringify(context.jobStatistics(message)));
const message = {version: 7, seed: 20260918, samples: 10000, series: [
  {label: "repeat cluster", unit: "round", denominator: 4, values: [
    {task: "repeat", value: -1, left: 3, right: 2},
    {task: "repeat", value: -1, left: 3, right: 2},
    {task: "other", value: 1, left: 1, right: 2}
  ]},
  {label: "empty", denominator: 4, values: []},
  {label: "pass delta", denominator: 3, mean: true, values: [
    {task: "a", value: 1}, {task: "b", value: 0}, {task: "c", value: -1}
  ]},
  {label: "constant", denominator: 1, values: [{task: "__proto__", value: 5, left: 0, right: 5}]}
]};
const result = calculate(message);
assert.deepEqual(result, calculate(message), "fixed seed must reproduce intervals");
assert.equal(result.version, 7);
assert.equal(result.results[0].tasks, 2, "repeats must remain one task cluster");
assert.equal(result.results[0].n, 3);
assert.equal(result.results[0].estimate, -1);
assert.equal(result.results[0].leftMedian, 3);
assert.equal(result.results[0].rightMedian, 2);
assert.deepEqual(result.results[0].interval, [-1, 1]);
assert.equal(result.results[1].estimate, null, "missing is not zero");
assert.equal(result.results[1].interval, null);
assert.equal(result.results[2].estimate, 0);
assert.equal(result.results[3].tasks, 1);
assert.deepEqual(result.results[3].interval, [5, 5]);
assert.equal(result.results[3].ratio, null, "zero baseline excluded from ratios");
console.log("Job statistics: deterministic intervals, task clusters, missing values, medians and zero baselines passed");
