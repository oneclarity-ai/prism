"""The org UI must show actual Prisms rather than the engine's seeded organization."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Optional JavaScript runtime unavailable")
def test_org_membership_identity_archives_and_reporting_links():
    result = subprocess.run(
        ["node", "--input-type=module"],
        cwd=Path(__file__).resolve().parents[1],
        input=r"""
import assert from 'node:assert/strict';
import { prismOrganization } from './app/static/js/prism-organization.js';
const chief='11111111-0000-0000-0000-000000000001';
const worker='22222222-0000-0000-0000-000000000002';
const draft='33333333-0000-0000-0000-000000000003';
const prisms = [
  {id:chief,name:'Chief of Staff',state:'active',is_chief_of_staff:true,job_role:'Chief of Staff',department:'Leadership',reports_to_prism_id:null},
  {id:worker,name:'Research Prism',state:'paused',job_role:'AI Researcher',department:'Research & Development',reports_to_prism_id:chief},
  {id:draft,name:'New Prism',state:'draft',job_role:'Marketing Specialist',department:'Marketing',reports_to_prism_id:chief},
  {id:'44444444-0000-0000-0000-000000000004',name:'Archived',state:'ARCHIVED'},
];
const agents=[{id:'unrelated',key:'seeded-qa',name:'New Prism'}];
const positions=[{id:'ceo',title:'CEO',holder_type:'human'},{id:'vacant',holder_type:'vacant'}];
const chart=prismOrganization(prisms,agents,positions,'Yash');
assert.deepEqual(chart.map(n=>n.title),['Yash','Chief of Staff','Research Prism','New Prism']);
assert.equal(chart[0].kind,'owner');
assert.equal(chart[0].prism_id,null);
assert.equal(chart[1].parent_id,chart[0].id);
assert.equal(chart[2].parent_id,chief);
assert.equal(chart[3].parent_id,chief,'An unprovisioned Prism still reports to Chief of Staff');
assert.equal(chart[2].department,'Research & Development');
assert.equal(chart[3].department,'Marketing');
assert.deepEqual(prismOrganization([...prisms].reverse(),agents,positions,'Yash'),chart,'Chat activity must not move the hierarchy');
assert.deepEqual(prismOrganization(prisms,[],[],'Yash'),chart,'Engine organization cannot override the saved Prism team');
assert.equal(prismOrganization([],agents,positions,'Yash').length,1,'An empty team still shows its owner');
const orphan=prismOrganization([prisms[0],{...prisms[2],reports_to_prism_id:'missing'}]);
assert.equal(orphan[2].parent_id,chief,'Missing or archived managers fall back to the Chief of Staff');
const cycle=prismOrganization([prisms[0],{...prisms[1],reports_to_prism_id:draft},{...prisms[2],reports_to_prism_id:worker}]);
for(const node of cycle){const seen=new Set([node.id]);let parent=node.parent_id;while(parent){assert.equal(seen.has(parent),false);seen.add(parent);parent=cycle.find(n=>n.id===parent)?.parent_id;}}

""",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
