import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { GenerateTestQueriesModal } from './GenerateTestQueriesModal'
it('submits the selected coverage once and exposes its checked state',()=>{
 const confirm=vi.fn()
 render(<GenerateTestQueriesModal onConfirm={confirm} onClose={vi.fn()} />)
 expect(screen.getByRole('radio',{name:/Standard/})).toBeChecked()
 fireEvent.click(screen.getByRole('radio',{name:/Exhaustive/}))
 expect(screen.getByRole('radio',{name:/Exhaustive/})).toBeChecked()
 fireEvent.click(screen.getByRole('button',{name:'Generate'}))
 fireEvent.click(screen.getByRole('button',{name:'Generate'}))
 expect(confirm).toHaveBeenCalledExactlyOnceWith('exhaustive')
})
it('closes on Escape without starting generation',()=>{
 const confirm=vi.fn(),close=vi.fn()
 render(<GenerateTestQueriesModal onConfirm={confirm} onClose={close} />)
 fireEvent.keyDown(screen.getByRole('dialog'),{key:'Escape'})
 expect(close).toHaveBeenCalledOnce();expect(confirm).not.toHaveBeenCalled()
})
