// .husky/commit-msg
const fs = require("fs");
const { execSync } = require("child_process");

const msgFile = process.argv[2];
const raw = fs.readFileSync(msgFile, "utf8");

// 첫 "의미 있는" 라인(빈줄/# 주석 제외)
const firstLine = raw
  .split("\n")
  .map((l) => l.trim())
  .find((l) => l && !l.startsWith("#"));

if (!firstLine) process.exit(0);

// Merge/Revert는 예외
if (firstLine.startsWith("Merge") || firstLine.startsWith("Revert")) process.exit(0);

// 최종 포맷 검사: [HSC-23] feat: 초기화
const ok = /^\[[A-Z]+-\d+\]\s+[a-z]+:\s+.+$/.test(firstLine);
if (!ok) {
  console.error(`최종 커밋 메시지 형식 위반: "${firstLine}"`);
  console.error(`Expected: [TICKET] <type>: <message>  (예: [HSC-23] feat: 초기화)`);
  process.exit(1);
}

// (선택) 브랜치 티켓과 커밋 메시지 티켓 일치 강제
let branch = "";
try {
  branch = execSync("git branch --show-current").toString().trim();
} catch {
  process.exit(0); // 브랜치 못 가져오면 검증만 하고 종료
}

const branchTicket = branch.match(/(?:^|\/)([A-Z]+-\d+)(?:$|[-/].*)/)?.[1];
const msgTicket = firstLine.match(/^\[([A-Z]+-\d+)\]/)?.[1];

if (branchTicket && msgTicket && branchTicket !== msgTicket) {
  console.error(`티켓 불일치: branch="${branchTicket}", message="${msgTicket}"`);
  process.exit(1);
}
