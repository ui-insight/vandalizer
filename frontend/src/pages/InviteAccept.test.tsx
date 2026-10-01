import { StrictMode } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
const api=vi.hoisted(() => ({ info:vi.fn(),accept:vi.fn(),refresh:vi.fn(),navigate:vi.fn() }))
let token='first'
vi.mock('@tanstack/react-router',()=>({useNavigate:()=>api.navigate,useSearch:()=>({token})}))
vi.mock('../hooks/useAuth',()=>({useAuth:()=>({user:{email:'member@example.test'},loading:false})}))
vi.mock('../hooks/useTeams',()=>({useTeams:()=>({refreshTeams:api.refresh})}))
vi.mock('../api/teams',()=>({getInviteInfo:api.info,acceptInvite:api.accept}))
vi.mock('../api/auth',()=>({getAuthConfig:vi.fn().mockResolvedValue({auth_methods:['password'],oauth_providers:[]})}))
import InviteAccept from './InviteAccept'
beforeEach(()=>{vi.clearAllMocks();token='first';api.info.mockReset().mockResolvedValue({team_name:'Research office',email:'member@example.test',role:'member',expired:false});api.accept.mockReset();api.refresh.mockResolvedValue(undefined)})
it('retries an unavailable invitation and accepts once',async()=>{
 api.info.mockRejectedValueOnce(new Error('Temporary read failure'))
 api.accept.mockResolvedValue({name:'Research office'})
 render(<InviteAccept />)
 expect(await screen.findByRole('alert')).toHaveTextContent('Temporary read failure')
 fireEvent.click(screen.getByRole('button',{name:'Retry invitation'}))
 await screen.findByText("You've joined Research office!")
 expect(api.accept).toHaveBeenCalledTimes(1)
})
it('keeps one acceptance in flight under StrictMode and retries a failed request',async()=>{
 let reject!: (error:Error)=>void
 api.accept.mockImplementationOnce(()=>new Promise((_,r)=>{reject=r})).mockResolvedValue({name:'Research office'})
 render(<StrictMode><InviteAccept /></StrictMode>)
 await waitFor(()=>expect(api.accept).toHaveBeenCalledTimes(1))
 await act(async()=>reject(new Error('Temporary acceptance failure')))
 fireEvent.click(await screen.findByRole('button',{name:'Retry invitation'}))
 await screen.findByText("You've joined Research office!")
 expect(api.accept).toHaveBeenCalledTimes(2)
})
it('ignores acceptance from a previous invitation after the token changes',async()=>{
 let resolve!: (result:unknown)=>void
 api.accept.mockImplementationOnce(()=>new Promise(r=>{resolve=r})).mockRejectedValueOnce(new Error('New invitation needs attention'))
 const {rerender}=render(<InviteAccept />)
 await waitFor(()=>expect(api.accept).toHaveBeenCalledWith('first'))
 token='second';rerender(<InviteAccept />)
 expect(await screen.findByRole('alert')).toHaveTextContent('New invitation needs attention')
 await act(async()=>resolve({name:'Old team'}))
 expect(api.refresh).not.toHaveBeenCalled()
 expect(screen.getByRole('alert')).toHaveTextContent('New invitation needs attention')
})
