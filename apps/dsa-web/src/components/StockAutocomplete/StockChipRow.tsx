import { cn } from '../../utils/cn';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { STOCK_AUTOCOMPLETE_TEXT } from '../../locales/featureText';

export type AssetFilter = 'all' | 'stock' | 'fund';

interface StockChipRowProps {
  value: AssetFilter;
  onChange: (next: AssetFilter) => void;
}

export function StockChipRow({ value, onChange }: StockChipRowProps) {
  const { language } = useUiLanguage();
  const t = STOCK_AUTOCOMPLETE_TEXT[language];

  const options: { value: AssetFilter; label: string }[] = [
    { value: 'all', label: t.assetFilterAll },
    { value: 'stock', label: t.assetFilterStock },
    { value: 'fund', label: t.assetFilterFund },
  ];

  return (
    <div className="flex flex-row gap-2 px-1 py-1 overflow-x-auto no-scrollbar">
      {options.map((option) => {
        const isActive = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              'px-3 py-0.5 text-xs rounded-full border transition-all duration-200 whitespace-nowrap',
              isActive
                ? 'bg-[var(--primary)]/10 border-[var(--primary)] text-[var(--primary)] font-medium shadow-sm'
                : 'bg-transparent border-[var(--border)] text-secondary-text hover:border-[var(--primary)]/50 hover:text-primary-text'
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export default StockChipRow;
