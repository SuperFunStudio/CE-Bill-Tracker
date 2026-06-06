'use client';
import { useEffect } from 'react';
import { BillDetailPanel } from '@/components/bills/BillDetailPanel';
import type { BillSummary } from '@/lib/types';

interface BillModalProps {
  bill: BillSummary | null;
  onClose: () => void;
}

export function BillModal({ bill, onClose }: BillModalProps) {
  // Close on Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  // Lock body scroll while open
  useEffect(() => {
    if (bill) document.body.style.overflow = 'hidden';
    else document.body.style.overflow = '';
    return () => { document.body.style.overflow = ''; };
  }, [bill]);

  if (!bill) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end md:items-start md:justify-end p-0 md:p-4"
      onClick={onClose}
    >
      {/* Dim overlay */}
      <div className="absolute inset-0 bg-black/60" />

      {/* Modal panel — bottom sheet on mobile, right-aligned panel on desktop */}
      <div
        className="relative z-10 w-full md:w-[480px] md:max-w-[40vw] max-h-[90dvh] overflow-y-auto rounded-t-2xl md:rounded-xl md:mt-16"
        onClick={e => e.stopPropagation()}
      >
        <BillDetailPanel bill={bill} onClose={onClose} />
      </div>
    </div>
  );
}
