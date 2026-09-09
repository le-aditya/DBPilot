import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { UploadPanel } from '../UploadPanel'

const apiUpload = vi.fn()

vi.mock('../../../lib/api', () => ({
  apiUpload: (...args: unknown[]) => apiUpload(...args),
}))

const ANALYSIS = {
  tables: [
    {
      name: 'people',
      source_filename: 'people.csv',
      sampled_rows: 2,
      columns: [
        {
          name: 'id',
          source_name: 'id',
          type: 'integer',
          nullable: false,
          samples: ['1'],
        },
      ],
    },
  ],
}

function csv(name = 'people.csv') {
  return new File(['id\n1\n'], name, { type: 'text/csv' })
}

describe('UploadPanel', () => {
  beforeEach(() => apiUpload.mockReset())

  it('invites a first file', () => {
    render(<UploadPanel projectId={1} onCommitted={vi.fn()} />)

    expect(screen.getByText(/add a csv/i)).toBeInTheDocument()
  })

  it('analyses the chosen file and shows the review step', async () => {
    apiUpload.mockResolvedValueOnce(ANALYSIS)
    render(<UploadPanel projectId={1} onCommitted={vi.fn()} />)

    await userEvent.upload(screen.getByLabelText(/csv files/i), csv())

    expect(await screen.findByText(/check the columns/i)).toBeInTheDocument()
    expect(apiUpload).toHaveBeenCalledWith('/projects/1/upload', expect.any(FormData))
  })

  it('sends the corrected spec with the files on commit', async () => {
    apiUpload
      .mockResolvedValueOnce(ANALYSIS)
      .mockResolvedValueOnce({ schema_name: 'user_1_x', table_count: 1, tables: [] })
    const onCommitted = vi.fn()
    render(<UploadPanel projectId={1} onCommitted={onCommitted} />)
    await userEvent.upload(screen.getByLabelText(/csv files/i), csv())
    await screen.findByText(/check the columns/i)

    await userEvent.click(screen.getByRole('button', { name: /create tables/i }))

    await waitFor(() => expect(onCommitted).toHaveBeenCalled())
    const body = apiUpload.mock.calls[1][1] as FormData
    expect(apiUpload.mock.calls[1][0]).toBe('/projects/1/upload/commit')
    expect(JSON.parse(body.get('spec') as string).tables[0].name).toBe('people')
    expect(body.getAll('files')).toHaveLength(1)
  })

  it('shows the server message when a file is refused', async () => {
    apiUpload.mockRejectedValueOnce(new Error('big.csv is larger than the 25 MB limit.'))
    render(<UploadPanel projectId={1} onCommitted={vi.fn()} />)

    await userEvent.upload(screen.getByLabelText(/csv files/i), csv('big.csv'))

    expect(await screen.findByRole('alert')).toHaveTextContent(/25 MB limit/)
  })
})
