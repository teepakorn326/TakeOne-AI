import { ShotDetail } from "@/components/shot-detail";
export default async function Page({ params }: { params: Promise<{ shotId: string }> }) {
  const { shotId } = await params;
  return <ShotDetail id={shotId} />;
}

