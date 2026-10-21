-- In the PDF a figure uses its vector PDF; the markdown on the web uses the SVG.
function Image(img)
  img.src = img.src:gsub('%.svg$', '.pdf')
  return img
end

-- The group in braces that starts at position i of s (s:sub(i, i) == '{'):
-- returns its contents and the position just after it.
local function group(s, i)
  local depth = 0
  for j = i, #s do
    local c = s:sub(j, j)
    if c == '{' then depth = depth + 1
    elseif c == '}' then
      depth = depth - 1
      if depth == 0 then return s:sub(i + 1, j - 1), j + 1 end
    end
  end
end

-- Pandoc writes tables as longtables, which break across pages. The tables of
-- the paper are short, so each becomes a floating table that stays whole.
function Table(tbl)
  if not FORMAT:match('latex') then return nil end
  local s = pandoc.write(pandoc.Pandoc({ tbl }), 'latex')
  local a = s:find('\\begin{longtable}[]', 1, true)
  if not a then return nil end
  local spec, k = group(s, a + #'\\begin{longtable}[]')
  local caption = ''
  local c = s:find('\\caption{', k, true)
  if c then
    local cap, after = group(s, c + #'\\caption')
    caption = cap
    k = s:find('\\tabularnewline', after, true) + #'\\tabularnewline'
  end
  local e = s:find('\\end{longtable}', k, true)
  local body = s:sub(k, e - 1)
  local first = body:find('\\endfirsthead', 1, true)
  if first then
    local last = body:find('\\endlastfoot', first, true)
    body = body:sub(1, first - 1) .. body:sub(last + #'\\endlastfoot')
  else
    body = body:gsub('\\endhead', '', 1)
    body = body:gsub('\\bottomrule\\noalign{}%s*\\endlastfoot', '', 1)
  end
  local out = '\\begin{table}[htbp]\n\\centering\\small\n'
  if caption ~= '' then out = out .. '\\caption{' .. caption .. '}\n' end
  out = out .. '\\begin{tabular}{' .. spec .. '}\n' .. body .. '\\bottomrule\\noalign{}\n\\end{tabular}\n\\end{table}\n'
  return pandoc.RawBlock('latex', out)
end

-- An unnumbered chapter (references, acknowledgements) sets its own running head.
function Header(h)
  if FORMAT:match('latex') and h.level == 1 and h.classes:includes('unnumbered') then
    return { h, pandoc.RawBlock('latex', '\\markboth{' .. pandoc.utils.stringify(h) .. '}{}') }
  end
end

-- File paths in running text may break after a slash.
function Code(c)
  if FORMAT:match('latex') and c.text:find('/') and c.text:match('^[%w%._/%-]+$') then
    return pandoc.RawInline('latex', '\\path|' .. c.text .. '|')
  end
end
