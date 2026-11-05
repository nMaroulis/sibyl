export type SemanticCoverage = {
  total: number;
  indexed: number;
  missing: number;
  partial: boolean;
};
export type SemanticStatus = {
  configured: boolean;
  revision: number;
  indexing: boolean;
  profile: {
    endpoint?: string;
    model?: string;
    model_digest?: string;
    server_version?: string;
    dimensions?: number;
  };
  coverage: Record<'all' | 'document' | 'news', SemanticCoverage>;
  limits: { passages: number; bytes: number };
  note: string;
};
