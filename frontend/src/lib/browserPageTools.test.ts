import toolsScript from '../../../chrome-extension/background/page-tools.js?raw'
import { expect, it } from 'vitest'
const { clickRef, typeRef } = new Function(`${toolsScript.replaceAll('export function', 'function')}\nreturn { clickRef, typeRef };`)()
it('refuses write-labelled controls before they can be clicked', () => {
  document.body.innerHTML = '<button data-vz-ref="1">Submit Invoice</button>'
  const button = document.querySelector('button')!
  Object.defineProperty(button, 'innerText', { value: button.textContent })
  let clicked = false
  button.addEventListener('click', () => { clicked = true })
  expect(clickRef(1)).toMatchObject({ error: 'blocked_write_action' })
  expect(clicked).toBe(false)
})
it('never types into a password field', () => {
  document.body.innerHTML = '<input data-vz-ref="2" type="password">'
  expect(typeRef(2, 'not-a-password')).toMatchObject({ error: 'not_a_text_field' })
  expect((document.querySelector('input') as HTMLInputElement).value).toBe('')
})
