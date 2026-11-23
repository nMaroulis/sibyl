export const fillBreakLabels = {
  full: 'Voided by Gemini',
  manual: 'Manual reversal · review required',
  unverified: 'Unverified trade break · review required',
};

export type FillBreak = keyof typeof fillBreakLabels;
export type FillBreakCounts = Partial<Record<FillBreak, number>>;

export function fillBreakSummary(counts: FillBreakCounts) {
  return (Object.keys(counts) as FillBreak[])
    .map((kind) => `${counts[kind]} ${fillBreakLabels[kind].toLowerCase()}`)
    .join(' · ');
}
