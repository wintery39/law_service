import { apiClient } from './apiClient';
import type { LegalBasisEntry } from '../types/legalBasis';

export const legalBasisService = {
  getLegalBasisByIds(ids: string[]) {
    const params = new URLSearchParams();
    ids.forEach((id) => params.append('ids', id));
    const query = params.toString();

    return apiClient.get<LegalBasisEntry[]>(`/legal-basis${query ? `?${query}` : ''}`);
  },
};
