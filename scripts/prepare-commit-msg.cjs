// .husky/prepare-commit-msg (또는 scripts/prepare-commit-msg.cjs)
const fs = require("fs");
const { execSync } = require("child_process");

const msgFile = process.argv[2];
const source = process.argv[3] || ""; // merge/squash 등

const raw = fs.readFileSync(msgFile, "utf8");
if (!raw) process.exit(0);

const firstLine = raw.split("\n")[0].trim();
if (!firstLine) process.exit(0);

// merge/squash/revert 류는 건드리지 않음
if (
  source === "merge" ||
  source === "squash" ||
  firstLine.startsWith("Merge") ||
  firstLine.startsWith("Revert")
) {
  process.exit(0);
}

// 현재 브랜치명
let branch = "";
try {
  branch = execSync("git branch --show-current").toString().trim();
} catch {
  process.exit(0);
}
if (!branch || branch === "HEAD") process.exit(0);

// 브랜치에서 티켓만 추출
const ticketMatch = branch.match(/(?:^|\/)([A-Z]+-\d+)(?:$|[-/].*)/);
if (!ticketMatch) process.exit(0);

const ticket = ticketMatch[1];

// 이미 [HSC-23] 있으면 중복 방지
if (firstLine.startsWith(`[${ticket}]`)) process.exit(0);

// 사용자가 "type: 메시지"로 썼을 때만 자동 조립
const mm = firstLine.match(/^([a-z]+)\s*:\s*(.+)$/);
if (!mm) process.exit(0); // 여기서 바꾸지 말고 commit-msg에서 막는 전략

const type = mm[1];
const rest = mm[2].trim();

// 최종 1줄: [HSC-23] feat: 초기화
const lines = raw.split("\n");
lines[0] = `[${ticket}] ${type}: ${rest}`;
fs.writeFileSync(msgFile, lines.join("\n"), "utf8");
