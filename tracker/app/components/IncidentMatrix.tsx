import { format } from "date-fns";

import { evaluateAll, MATCH_GLYPH, MATCH_LABEL } from "../lib/definitions";
import type { Incident } from "@/types/data";

const MARK_COLOR = { yes: "#d8d5cf", unknown: "#8b8880", no: "#4a4945" } as const;

export default function IncidentMatrix({ incidents }: { incidents: Incident[] }) {
  return (
    <div className="matrix">
      <div className="head">DATE</div>
      <div className="head">LOCATION</div>
      <div className="head right">KILL/INJ</div>
      <div className="head center">GVA</div>
      <div className="head center">MJ</div>

      {incidents.map((incident) => {
        const match = evaluateAll(incident);
        return (
          <Row key={incident.id} incident={incident} gva={match.gva} mj={match.mother_jones} />
        );
      })}
    </div>
  );
}

function Row({
  incident,
  gva,
  mj,
}: {
  incident: Incident;
  gva: keyof typeof MARK_COLOR;
  mj: keyof typeof MARK_COLOR;
}) {
  return (
    <>
      <div className="cell num" style={{ color: "#8b8880" }}>
        {format(new Date(incident.date), "d MMM")}
      </div>
      <div className="cell place">
        {incident.city}, {incident.state}
      </div>
      <div className="cell num right" style={{ color: "#d8d5cf" }}>
        {incident.killed}/{incident.injured}
      </div>
      <div className="cell mark" style={{ color: MARK_COLOR[gva] }} title={MATCH_LABEL[gva]}>
        {MATCH_GLYPH[gva]}
      </div>
      <div className="cell mark" style={{ color: MARK_COLOR[mj] }} title={MATCH_LABEL[mj]}>
        {MATCH_GLYPH[mj]}
      </div>
    </>
  );
}
