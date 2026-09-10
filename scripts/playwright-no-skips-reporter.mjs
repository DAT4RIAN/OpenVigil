export default class NoSkippedReporter {
  constructor() {
    this.skipped = [];
  }

  onTestEnd(test, result) {
    if (result.status === "skipped") this.skipped.push(test.titlePath().join(" › "));
  }

  onEnd() {
    if (process.env.WINDOPS_FAIL_ON_SKIPPED !== "1" || this.skipped.length === 0) return;
    console.error(`Required Playwright run skipped ${this.skipped.length} test(s):`);
    for (const title of this.skipped) console.error(`- ${title}`);
    return { status: "failed" };
  }
}
