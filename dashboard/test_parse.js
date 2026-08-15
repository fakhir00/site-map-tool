const summary = `{
  "Primary Keyword": "0DTE Trading Strategy",
  "Industry / Niche": "Futures Trading",
  "Core Action": "Educate and provide tools for trading zero-days-to-expiration futures contracts.",
  "Target Audience": "Traders interested in short-term futures trading strategies.",
  "Capabilities (DOES)": "Offers strategies, educational resources, tools for analysis, and market commentary.",
  "Hard Boundaries (DOES NOT)": "Does not provide long-term investment strategies or advice on other types of financial instruments."
}`;
const cleanSummary = summary.replace(/^```json\s*/, '').replace(/```\s*$/, '').trim();
console.log("clean:", cleanSummary);
try {
  const parsed = JSON.parse(cleanSummary);
  console.log("Success:", parsed);
} catch (e) {
  console.log("Error:", e);
}
