import { EpisodeDetail } from "@/components/episode-detail";
export default async function Page({ params }: { params: Promise<{ id: string; episodeId: string }> }) {
  const { id, episodeId } = await params;
  return <EpisodeDetail seriesId={id} episodeId={episodeId} />;
}

