import ReactFlow, { Node, Edge } from "reactflow";
import "reactflow/dist/style.css";

export function BusinessGraph({ model }: { model: any }) {
  const flows = model?.flows || [];
  const nodes: Node[] = flows.map((f: any, i: number) => ({
    id: f.id || `f${i}`, position: { x: 80, y: i * 90 }, data: { label: f.name },
  }));
  const edges: Edge[] = flows.flatMap((f: any, i: number) =>
    (f.steps || []).map((_: any, j: number) => ({
      id: `${f.id}-${j}`, source: f.id || `f${i}`, target: flows[i + 1]?.id || `f${i + 1}` || f.id,
    })).filter((e: Edge) => e.target !== e.source));
  return <ReactFlow nodes={nodes} edges={edges} fitView />;
}
