export interface SupportedDocumentDefinition {
  title: string;
  type: string;
  order: number;
  label: string;
}

export const DISCIPLINARY_DOCUMENT_CATALOG: SupportedDocumentDefinition[] = [
  {
    title: '사실결과조사보고',
    type: 'fact_finding_report',
    order: 1,
    label: '사실 조사',
  },
  {
    title: '출석통지서',
    type: 'attendance_notice',
    order: 2,
    label: '당사자 통지',
  },
  {
    title: '위원회 참고 자료',
    type: 'committee_reference',
    order: 3,
    label: '심의 참고',
  },
  {
    title: '징계의결서/처분서',
    type: 'disciplinary_resolution',
    order: 4,
    label: '최종 의결',
  },
];

const documentTypeLabelMap = new Map(
  DISCIPLINARY_DOCUMENT_CATALOG.map((item) => [item.type, item.label]),
);

export function getDocumentTypeLabel(type: string) {
  return documentTypeLabelMap.get(type) ?? type;
}
