import exampleSkillJson from '../data/browser-demo-skill.json?raw'

const example = JSON.parse(exampleSkillJson).items[0] as { title: string; extraction_config: { content: string } }
export function browserSkillTemplate(demo = false) {
  return demo ? {
    example: true,
    title: example.title,
    when: 'Collect a sourced research snapshot from the University of Idaho public website.',
    instructions: example.extraction_config.content,
  } : {
    example: false,
    title: 'Collect figures from websites',
    when: 'Collect figures from the websites and award numbers I specify.',
    instructions: `Sites to visit
Replace this with each exact URL (for example https://finance.example.edu/awards).

What to search for
Ask me for the award numbers. Name the search field, Search button, and tabs by the exact labels shown on the page.

Values to record
List each figure and its exact page label here. Use one record_value per figure, exactly as shown.

Sign-in and permissions
Stop if login_required or unapproved_site is returned. Ask me to sign in in the working tab and tell you to continue. Never ask for passwords. Only read sites I allow. The tools refuse to submit or change anything.

Missing values and calculations
Mark missing figures Not found; never guess. Use calculate for math.

Final table
One row per award, one column per recorded figure, plus Sources with a link for every figure.`
  }
}
