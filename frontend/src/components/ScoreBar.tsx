import { scoreBarColorClass } from "@/lib/format";

export function ScoreBar({
  label,
  score,
  detail,
}: {
  label: string;
  score: number;
  detail?: string;
}) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-sm">
        <span className="font-medium text-zinc-300">{label}</span>
        <span className="text-zinc-400">
          {score.toFixed(0)}
          {detail && <span className="ml-1 text-xs text-zinc-500">{detail}</span>}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800">
        <div
          className={`h-full rounded-full ${scoreBarColorClass(score)}`}
          style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
        />
      </div>
    </div>
  );
}
