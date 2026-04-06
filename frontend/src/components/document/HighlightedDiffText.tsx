type DiffKind = 'same' | 'removed' | 'added';

interface DiffPart {
  kind: DiffKind;
  text: string;
}

interface HighlightedDiffTextProps {
  originalText: string;
  proposedText: string;
  variant: 'original' | 'proposed';
  emptyText?: string;
  className?: string;
}

function tokenize(text: string) {
  return text.match(/\S+|\s+/g) ?? [];
}

function mergeParts(parts: DiffPart[]) {
  if (parts.length === 0) {
    return parts;
  }

  const merged: DiffPart[] = [parts[0]];
  for (let index = 1; index < parts.length; index += 1) {
    const current = parts[index];
    const previous = merged[merged.length - 1];

    if (previous.kind === current.kind) {
      previous.text += current.text;
      continue;
    }

    merged.push({ ...current });
  }

  return merged;
}

function buildDiffParts(originalText: string, proposedText: string) {
  const originalTokens = tokenize(originalText);
  const proposedTokens = tokenize(proposedText);
  const dp = Array.from({ length: originalTokens.length + 1 }, () =>
    Array.from({ length: proposedTokens.length + 1 }, () => 0),
  );

  for (let originalIndex = 1; originalIndex <= originalTokens.length; originalIndex += 1) {
    for (let proposedIndex = 1; proposedIndex <= proposedTokens.length; proposedIndex += 1) {
      if (originalTokens[originalIndex - 1] === proposedTokens[proposedIndex - 1]) {
        dp[originalIndex][proposedIndex] = dp[originalIndex - 1][proposedIndex - 1] + 1;
        continue;
      }

      dp[originalIndex][proposedIndex] = Math.max(
        dp[originalIndex - 1][proposedIndex],
        dp[originalIndex][proposedIndex - 1],
      );
    }
  }

  const operations: DiffPart[] = [];
  let originalIndex = originalTokens.length;
  let proposedIndex = proposedTokens.length;

  while (originalIndex > 0 && proposedIndex > 0) {
    if (originalTokens[originalIndex - 1] === proposedTokens[proposedIndex - 1]) {
      operations.push({ kind: 'same', text: originalTokens[originalIndex - 1] });
      originalIndex -= 1;
      proposedIndex -= 1;
      continue;
    }

    if (dp[originalIndex - 1][proposedIndex] >= dp[originalIndex][proposedIndex - 1]) {
      operations.push({ kind: 'removed', text: originalTokens[originalIndex - 1] });
      originalIndex -= 1;
      continue;
    }

    operations.push({ kind: 'added', text: proposedTokens[proposedIndex - 1] });
    proposedIndex -= 1;
  }

  while (originalIndex > 0) {
    operations.push({ kind: 'removed', text: originalTokens[originalIndex - 1] });
    originalIndex -= 1;
  }

  while (proposedIndex > 0) {
    operations.push({ kind: 'added', text: proposedTokens[proposedIndex - 1] });
    proposedIndex -= 1;
  }

  const reversedOperations = [...operations].reverse();
  const originalParts = mergeParts(reversedOperations.filter((part) => part.kind !== 'added'));
  const proposedParts = mergeParts(reversedOperations.filter((part) => part.kind !== 'removed'));

  return { originalParts, proposedParts };
}

function getPartClassName(kind: DiffKind, variant: 'original' | 'proposed') {
  if (kind === 'same') {
    return '';
  }

  if (variant === 'original') {
    return 'rounded bg-amber-200/80 decoration-rose-500 line-through';
  }

  return 'rounded bg-lime-200/80';
}

export function HighlightedDiffText({
  originalText,
  proposedText,
  variant,
  emptyText,
  className,
}: HighlightedDiffTextProps) {
  const { originalParts, proposedParts } = buildDiffParts(originalText, proposedText);
  const parts = variant === 'original' ? originalParts : proposedParts;
  const resolvedEmptyText = emptyText ?? (variant === 'original' ? '해당 없음' : '삭제 제안');

  if (parts.length === 0 || parts.every((part) => !part.text)) {
    return <span className={className ? `${className} text-slate-400` : 'text-slate-400'}>{resolvedEmptyText}</span>;
  }

  return (
    <>
      {parts.map((part, index) => (
        <span key={`${variant}-${index}`} className={className ? `${className} ${getPartClassName(part.kind, variant)}` : getPartClassName(part.kind, variant)}>
          {part.text}
        </span>
      ))}
    </>
  );
}
